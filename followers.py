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
FOLLOWING_PREFIX = 'Following @{screen_name} ({id}): '
UNFOLLOWING_PREFIX = 'Unfollowing @{screen_name} ({id}): '
FOLLOW_UNELIGIBLE = STATUS_LEFT + FOLLOWING_PREFIX + 'uneligible.'
FOLLOW_THROTTLE = STATUS_LEFT + FOLLOWING_PREFIX + 'throttled.'
FOLLOW_ERROR = STATUS_LEFT + FOLLOWING_PREFIX + 'error: {exc}'
FOLLOW_SUCCESS = STATUS_LEFT + FOLLOWING_PREFIX + 'success!'
UNFOLLOW_ERROR = STATUS_LEFT + UNFOLLOWING_PREFIX + 'error: {exc}'
UNFOLLOW_SUCCESS = STATUS_LEFT + UNFOLLOWING_PREFIX + 'success!'


class Parallel(object):
    def __init__(self, func, things, num_threads):
        self.queue = Queue()
        for _ in range(num_threads):
            thread = threading.Thread(target=func, args=(self.queue,))
            thread.daemon = True
            thread.start()

        for thing in things:
            self.queue.put(thing)

    def start(self):
        self.queue.join()


def mass_follow(screen_name=None, min_followers=50, last_post_delta=7,
                not_my_followers=True, lang=None, num_threads=50,
                type='followers'):
    if not screen_name:
        screen_name = twitter.me.screen_name

    if type == 'friends':
        func = twitter.api.friends
    elif type == 'followers':
        func = twitter.api.followers
    else:
        raise ValueError
    # download the list of users to follow
    users = []
    for page in tweepy.Cursor(func, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            if user.following or user.follow_request_sent:
                continue
            if user.id == twitter.me.id:
                continue
            if min_followers and user.followers_count < min_followers:
                continue
            if lang and lang != user.lang:
                continue
            if not_my_followers and user.followed_by:
                continue
            if last_post_delta:
                if not hasattr(user, 'status'):
                    continue
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
                except tweepy.error.TweepError as exc:
                    if exc.api_code == 161:
                        print(FOLLOW_THROTTLE
                              .format(left=queue.qsize() + 1,
                                      screen_name=user.screen_name,
                                      id=user.id))
                    else:
                        print(FOLLOW_ERROR
                              .format(left=queue.qsize() + 1,
                                      screen_name=user.screen_name,
                                      id=user.id,
                                      exc=str(exc)))
                else:
                    print(FOLLOW_SUCCESS
                          .format(left=queue.qsize() + 1,
                                  screen_name=user.screen_name,
                                  id=user.id))
                    break
            queue.task_done()

    parallel = Parallel(follow, users, num_threads)
    parallel.start()


def follow_from_file(filename, ids=False, num_threads=50):
    with open(filename) as file:
        users = [line.rstrip('\n') for line in file]

    if ids:
        users = [int(user) for user in users]

    random.shuffle(users)

    def follow(queue):
        while True:
            user = queue.get()

            # first check if the user is eligible at all
            try:
                if type(user) == int:
                    user_obj = twitter.api.get_user(user_id=user)
                elif type(user) == str:
                    user_obj = twitter.api.get_user(screen_name=user)
            except tweepy.error.TweepError:
                queue.task_done()
                continue
            if not is_eligible(user_obj):
                print(FOLLOW_UNELIGIBLE.format(left=queue.qsize() + 1,
                                               screen_name=user, id=user))
                queue.task_done()
                continue

            while True:
                try:
                    if type(user) == int:
                        twitter.api.create_friendship(user_id=user)
                    elif type(user) == str:
                        twitter.api.create_friendship(screen_name=user)
                except tweepy.error.TweepError as exc:
                    if exc.api_code == 161:
                        print(FOLLOW_THROTTLE.format(left=queue.qsize() + 1,
                                                     screen_name=user,
                                                     id=user))
                    else:
                        print(FOLLOW_ERROR.format(left=queue.qsize() + 1,
                                                  screen_name=user,
                                                  id=user, exc=str(exc)))
                        # if exc.api_code in (108, 160):
                        break
                else:
                    print(FOLLOW_SUCCESS.format(left=queue.qsize() + 1,
                                                screen_name=user, id=user))
                    break
            queue.task_done()

    parallel = Parallel(follow, users, num_threads)
    parallel.start()


def mass_unfollow(only_followers=False, only_unfollowers=False,
                  num_threads=50):
    if only_followers and only_unfollowers:
        raise ValueError('choose either only_followers or only_unfollowers!')

    users = []
    count = 100 if only_followers or only_unfollowers else 200
    for page in tweepy.Cursor(twitter.api.friends, count=count).pages():
        if only_followers or only_unfollowers:
            user_ids = [user.id for user in page]
            for user in twitter.api._lookup_friendships(user_ids):
                if only_followers:
                    if user.is_followed_by:
                        users.append(user)
                if only_unfollowers:
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
            except tweepy.error.TweepError as exc:
                print(UNFOLLOW_ERROR
                      .format(left=queue.qsize() + 1,
                              screen_name=user.screen_name,
                              id=user.id,
                              exc=str(exc)))
            else:
                print(UNFOLLOW_SUCCESS
                      .format(left=queue.qsize() + 1,
                              screen_name=user.screen_name,
                              id=user.id))
            queue.task_done()

    parallel = Parallel(unfollow, users, num_threads)
    parallel.start()


def print_list(screen_name=None, type='friends', format='simple'):
    screen_name = screen_name or twitter.me.screen_name

    if format not in {'simple', 'csv'}:
        raise ValueError('invalid format %s' % format)

    if type == 'friends':
        func = twitter.api.friends
    elif type == 'followers':
        func = twitter.api.followers
    else:
        raise ValueError

    if format == 'csv':
        print('user,friends,followers')
    for page in tweepy.Cursor(func, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            if format == 'simple':
                print(user.screen_name)
            elif format == 'csv':
                print('%s,%d,%d' % (user.screen_name,
                                    user.friends_count,
                                    user.followers_count))


# from akari
def is_eligible(user):
    """checks if a user is eligible to be followed."""
    if user.friends_count > 5000:
        return False
    if (user.followers_count > 5000 and
            user.friends_count / user.followers_count > 0.7):
        return False

    return True
