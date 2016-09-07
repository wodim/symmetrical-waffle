from tweepy import OAuthHandler
from tweepy import API

import config


class Twitter(object):
    def __init__(self,
                 consumer_key, consumer_secret,
                 access_token, access_token_secret):
        self.auth = OAuthHandler(consumer_key, consumer_secret)
        self.auth.set_access_token(access_token, access_token_secret)
        self.api = API(self.auth)
        self.me = self.api.me()

twitter = Twitter(config.CONSUMER_KEY,
                  config.CONSUMER_SECRET,
                  config.ACCESS_TOKEN,
                  config.ACCESS_TOKEN_SECRET)
