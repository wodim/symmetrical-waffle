import random
import sys


try:
    filename = sys.argv[1]
except IndexError:
    filename = 'config.txt'

with open(filename) as fp:
    tokens = [x.rstrip('\n') for x in fp.readlines()]
    _, CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET = \
        random.choice(tokens).split(',')
