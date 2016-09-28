from datetime import datetime, timedelta
from queue import Queue
import random
import threading

import tweepy

from twitter import twitter


SOURCES_WHITELIST = ('Twitter for Android',
                     'Twitter for iPad',
                     'Twitter for iPhone',
                     'Twitter for Mac',
                     'Twitter for Windows',
                     'Twitter for Windows Phone',
                     'Twitter Web Client',
                     'TweetDeck',
                     'Tweetbot for iΟS',
                     'Tweetbot for Mac',
                     'Mobile Web',
                     'Mobile Web (M2)',
                     'Mobile Web (M5)')
STATUS_LEFT = '{left:> 6d} left | '
FOLLOW_THROTTLE = STATUS_LEFT + 'Following @{screen_name} ({id}): throttled.'
FOLLOW_ERROR = STATUS_LEFT + 'Following @{screen_name} ({id}): error: {e}'
FOLLOW_SUCCESS = STATUS_LEFT + 'Following @{screen_name} ({id}): success!'
UNFOLLOW_ERROR = STATUS_LEFT + 'Unfollowing @{screen_name} ({id}): error: {e}'
UNFOLLOW_SUCCESS = STATUS_LEFT + 'Unfollowing @{screen_name} ({id}): success!'


class Parallel(object):
    def __init__(self, func, things, num_threads):
        self.queue = Queue()
        for i in range(num_threads):
            thread = threading.Thread(target=func, args=(self.queue,))
            thread.daemon = True
            thread.start()

        for thing in things:
            self.queue.put(thing)

    def start(self):
        self.queue.join()


def follow_followers(screen_name=None, **kwargs):
    screen_name = screen_name or twitter.me.screen_name
    min_followers = kwargs.get('min_followers', 50)
    last_post_delta = kwargs.get('last_post_delta', 7)

    # download the list of users to follow
    users = []
    for page in tweepy.Cursor(twitter.api.followers, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            if user.following or user.follow_request_sent:
                continue
            if user.id == twitter.me.id:
                continue
            if min_followers and user.followers_count < min_followers:
                continue
            if not hasattr(user, 'status'):
                continue
            if last_post_delta:
                if (user.status.created_at <
                        datetime.now() - timedelta(days=last_post_delta)):
                    continue
                if user.status.source not in SOURCES_WHITELIST:
                    continue
            users.append(user)
        print('{len} users downloaded...'.format(len=len(users)))
    print('Finished: {len} users total'.format(len=len(users)))
    random.shuffle(users)

    def follow(queue):
        while True:
            user = queue.get()
            while True:
                try:
                    user.follow()
                except tweepy.error.TweepError as e:
                    if e.api_code == 161:
                        print(FOLLOW_THROTTLE
                              .format(left=queue.qsize(),
                                      screen_name=user.screen_name,
                                      id=user.id))
                    else:
                        print(FOLLOW_ERROR
                              .format(left=queue.qsize(),
                                      screen_name=user.screen_name,
                                      id=user.id,
                                      e=str(e)))
                else:
                    print(FOLLOW_SUCCESS
                          .format(left=queue.qsize(),
                                  screen_name=user.screen_name,
                                  id=user.id))
                    break
            queue.task_done()

    parallel = Parallel(follow, users, kwargs.get('num_threads', 50))
    parallel.start()


def mass_unfollow(only_unfollowers=False, **kwargs):
    users = []
    count = 100 if only_unfollowers else 200
    for page in tweepy.Cursor(twitter.api.friends, count=count).pages():
        if only_unfollowers:
            user_ids = [user.id for user in page]
            for user in twitter.api._lookup_friendships(user_ids):
                if not user.is_followed_by:
                    users.append(user)
        else:
            users.extend(page)

        print('{len} users downloaded...'.format(len=len(users)))
    print('Finished: {len} users total'.format(len=len(users)))

    def unfollow(queue):
        while True:
            user = queue.get()
            try:
                twitter.api.destroy_friendship(user.id)
            except tweepy.error.TweepError as e:
                print(UNFOLLOW_ERROR
                      .format(left=queue.qsize(),
                              screen_name=user.screen_name,
                              id=user.id,
                              e=str(e)))
            else:
                print(UNFOLLOW_SUCCESS
                      .format(left=queue.qsize(),
                              screen_name=user.screen_name,
                              id=user.id))
            queue.task_done()

    parallel = Parallel(unfollow, users, kwargs.get('num_threads', 50))
    parallel.start()


def get_list(screen_name=None, type='friends'):
    screen_name = screen_name or twitter.me.screen_name
    if type == 'friends':
        func = twitter.api.friends
    elif type == 'followers':
        func = twitter.api.followers
    else:
        raise ValueError
    for page in tweepy.Cursor(func, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            print(user.screen_name)
