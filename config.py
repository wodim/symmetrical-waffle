import random


with open('config.txt') as fp:
    tokens = [x.rstrip('\n') for x in fp.readlines()]
    _, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET = \
        random.choice(tokens).split(',')
