#!/usr/bin/env python

# Copyright 2016 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START imports]
import os
import re
import time
import urllib

from amazonproduct import API
from bs4 import BeautifulSoup
from google.appengine.api import users
from google.appengine.ext import ndb
#from lxml import etree

import jinja2
import webapp2

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)
# [END imports]

DEFAULT_GUESTBOOK_NAME = 'default_guestbook'


# We set a parent key on the 'Greetings' to ensure that they are all
# in the same entity group. Queries across the single entity group
# will be consistent. However, the write rate should be limited to
# ~1/second.

def guestbook_key(guestbook_name=DEFAULT_GUESTBOOK_NAME):
    """Constructs a Datastore key for a Guestbook entity.

    We use guestbook_name as the key.
    """
    return ndb.Key('Guestbook', guestbook_name)


# [START greeting]
class Author(ndb.Model):
    """Sub model for representing an author."""
    identity = ndb.StringProperty(indexed=False)
    email = ndb.StringProperty(indexed=False)


class Greeting(ndb.Model):
    """A main model for representing an individual Guestbook entry."""
    author = ndb.StructuredProperty(Author)
    content = ndb.StringProperty(indexed=False)
    date = ndb.DateTimeProperty(auto_now_add=True)
# [END greeting]

class Recipe(ndb.Model):
    user_id = ndb.StringProperty(indexed=True)
    title = ndb.StringProperty(indexed=True)
    ingredients = ndb.StringProperty(indexed=False)
    directions = ndb.StringProperty(indexed=False)
    date = ndb.DateTimeProperty(auto_now_add=True)

# [START main_page]
class MainPage(webapp2.RequestHandler):

    def get(self):
        guestbook_name = self.request.get('guestbook_name',
                                          DEFAULT_GUESTBOOK_NAME)
        greetings_query = Greeting.query(
            ancestor=guestbook_key(guestbook_name)).order(-Greeting.date)
        greetings = greetings_query.fetch(10)

        user = users.get_current_user()

        if user:
            recipe_query = Recipe.query().filter(ndb.GenericProperty("user_id") == user.user_id()).order(-Recipe.date)
            recipes = recipe_query.fetch(10)
            url = users.create_logout_url(self.request.uri)
            url_linktext = 'Logout'
        else:
            recipes = None
            url = users.create_login_url(self.request.uri)
            url_linktext = 'Login'

        template_values = {
            'user': user,
            'recipes': recipes,
            'guestbook_name': urllib.quote_plus(guestbook_name),
            'url': url,
            'url_linktext': url_linktext,
        }

        template = JINJA_ENVIRONMENT.get_template('index.html')
        self.response.write(template.render(template_values))
# [END main_page]

# [START guestbook]
class Guestbook(webapp2.RequestHandler):

    def post(self):
        # We set the same parent key on the 'Greeting' to ensure each
        # Greeting is in the same entity group. Queries across the
        # single entity group will be consistent. However, the write
        # rate to a single entity group should be limited to
        # ~1/second.
        guestbook_name = self.request.get('guestbook_name',
                                          DEFAULT_GUESTBOOK_NAME)
        greeting = Greeting(parent=guestbook_key(guestbook_name))

        if users.get_current_user():
            greeting.author = Author(
                    identity=users.get_current_user().user_id(),
                    email=users.get_current_user().email())

        #NEW CODE Here
        link = self.request.get('content')
        if link and link.strip():
            link_contents = urllib.urlopen(link)
            recipe_contents = link_contents.read()
            bs = BeautifulSoup(recipe_contents, "html.parser")

            #Get recipe ingredients
            ingreds = bs.find_all(itemprop='ingredients')
            ingredient_list = ""

            for ingredient in ingreds:
                ingredient_list += ingredient.text + "|"

            if ingredient_list.endswith('|'):
                ingredient_list = ingredient_list[:-1]

            #Get recipe title
            recipe_title = bs.title.string

            #Get recipe directions
            recipe_directions_unparsed = bs.find(itemprop='recipeInstructions')
            recipe_directions_result = ""
            for direction_tag in recipe_directions_unparsed.contents:
                if direction_tag.string and direction_tag.string.strip():
                    recipe_directions_result += direction_tag.string + ","
            if (recipe_directions_result.endswith(',')):
                recipe_directions_result = recipe_directions_result[:-1]

            #Save recipe with a user tied to it
            if (users.get_current_user()):
                recipe = Recipe()   
                recipe.user_id = users.get_current_user().user_id()
                recipe.title = recipe_title
                recipe.ingredients = ingredient_list
                recipe.directions = recipe_directions_result
                recipe.put()

            greeting.content = ingredient_list
            greeting.put()

            """template_values = {
                'content': recipe_contents
            }

            template = JINJA_ENVIRONMENT.get_template('sign.html')
            self.response.write(template.render(template_values))"""
        query_params = {'guestbook_name': guestbook_name}
        time.sleep(0.5)
        self.redirect('/?' + urllib.urlencode(query_params))

# [END guestbook]

#START Collector that sums up all ingredients
class Collector(webapp2.RequestHandler):
    def get(self):
        user = users.get_current_user()
        if user:
            recipe_query = Recipe.query().filter(ndb.GenericProperty("user_id") == user.user_id()).order(-Recipe.date)
            recipes = recipe_query.fetch(10)

        ingredient_dictionary = {}

        # amazonApi = API(locale='us')

        for recipe in recipes:
            #After it's split it's this: 1 (32 ounce) package frozen hash brown potatoes
            single_whole_ingredient = recipe.ingredients.split('|')

            for single_ingredient in single_whole_ingredient:
                #After it's split it's this: [1, (32, ounce), package, frozen, hash, brown, potatoes]
                single_ingredient_quantity_and_name = single_ingredient.split(' ')
                quantity = 0
                ingredient_name = ""

                for single_ingredient_base_unit in single_ingredient_quantity_and_name:
                    if (RepresentsInt(single_ingredient_base_unit)):
                        quantity = int(single_ingredient_base_unit)
                    else:
                        ingredient_name += single_ingredient_base_unit + " "

                if ingredient_name in ingredient_dictionary:
                    ingredient_dictionary[ingredient_name][0] += quantity
                else:
                    ingredient_dictionary.setdefault(ingredient_name, [])
                    ingredient_dictionary[ingredient_name].append(quantity)
                    base_url = "https://www.amazon.com/s/ref=nb_sb_noss?url=search-alias%3Damazonfresh&field-keywords="
                    last_two_words_ingredients = ingredient_name.split(' ')
                    search_url = base_url + last_two_words_ingredients[len(last_two_words_ingredients)-3] + "+" + last_two_words_ingredients[len(last_two_words_ingredients)-2]
                    ingredient_dictionary[ingredient_name].append(search_url)

               # amazonApi.item_search('GourmetFood', Keywords=ingredient_name)

        template_values = {
            'ingredient_totals': ingredient_dictionary,
        }

        template = JINJA_ENVIRONMENT.get_template('collect.html')
        self.response.write(template.render(template_values))
#END Collector

class Deleter(webapp2.RequestHandler):
    def post(self):
        user = users.get_current_user()
        if user:
            recipe_query = Recipe.query().filter(ndb.GenericProperty("user_id") == user.user_id()).order(-Recipe.date)
            recipes = recipe_query.fetch(10)

        for recipe in recipes:
            recipe.key.delete()

        time.sleep(0.5)
        self.redirect('/')

#
def RepresentsInt(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False

# [START app]
app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/sign', Guestbook),
    ('/collect', Collector),
    ('/delete', Deleter),
], debug=True)
# [END app]
