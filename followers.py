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
STATUS_INFO = ('{tpc:>6.1%} done. '
               '{users:>5} users downloaded ({fpc:.1%} selected)')
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

        for thing in things:
            self.queue.put(thing)

        for _ in range(num_threads):
            thread = threading.Thread(target=func, args=(self.queue,))
            thread.daemon = True
            thread.start()

    def start(self):
        self.queue.join()


def mass_follow(screen_name=None, min_followers=50, last_post_delta=7,
                not_my_followers=True, lang=None, num_threads=50,
                type='followers', check_eligibility=True):
    """Massively follow a list of users taken from another account.

    Args:
        screen_name: screen name of the user we'll get the list from. can be
            omitted, and then it defaults to yourself.
        min_followers: minimum amount of followers a user has to have to be
            followed.
        last_post_delta: the user has to have posted something in the last X
            days using one of the clients hardcoded in SOURCES_WHITELIST to be
            followed. useful to ignore dormant/spammy accounts.
        not_my_followers: don't follow users who already follow you.
        lang: only follow users who use the twitter app/website in a certain
            language, such as "en", "de", etc. can be a str or a list of
            strs
        num_threads: number of threads that will be launched to follow users
            in parallel. doesn't affect the retrieval of the list.
        type: list of users that we'll download from screen_name: can be either
            his 'followers' or his 'friends' (following).
        check_eligibility: check the eligibility of the user using
            is_eligible() below. that function filters obvious spambots.
    """
    if not screen_name:
        screen_name = twitter.me.screen_name

    if type in ('friends', 'following'):
        func = twitter.api.friends
        total = twitter.api.get_user(screen_name).friends_count
    elif type == 'followers':
        func = twitter.api.followers
        total = twitter.api.get_user(screen_name).followers_count
    else:
        raise ValueError('"type" must be either "friends" or "followers"')
    # download the list of users to follow
    filtered_users = []
    all_users = []
    for page in tweepy.Cursor(func, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            all_users.append(user)
            if user.following or user.follow_request_sent:
                continue
            if user.id == twitter.me.id:
                continue
            if min_followers and user.followers_count < min_followers:
                continue
            if check_eligibility and not _is_eligible(user):
                continue
            if lang:
                if isinstance(lang, (list, set, tuple)):
                    if user.lang not in lang:
                        continue
                elif isinstance(lang, str):
                    if user.lang != lang:
                        continue
                else:
                    raise ValueError('lang must be either a str or a list')
            if not_my_followers and user.followed_by:
                continue
            if last_post_delta:
                if not hasattr(user, 'status'):
                    continue
                delta_min = datetime.now() - timedelta(days=last_post_delta)
                if user.status.created_at < delta_min:
                    continue
                if user.status.source not in SOURCES_WHITELIST:
                    continue
            filtered_users.append(user)
        print(STATUS_INFO.format(users=len(filtered_users),
                                 tpc=len(all_users) / total,
                                 fpc=len(filtered_users) / len(all_users)))
    print('Finished: {len} users total'.format(len=len(filtered_users)))
    random.shuffle(filtered_users)

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

    parallel = Parallel(follow, filtered_users, num_threads)
    parallel.start()


def follow_from_file(filename, ids=False, num_threads=50):
    """Massively follow a list of users taken from a file.

    Args:
        filename: name of the file.
        ids: true if the list contains a list of ids (account numbers), false
            if it's screen names instead.
        num_threads: number of threads that will be launched to follow users
            in parallel.

    """
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
                if isinstance(user, int):
                    user_obj = twitter.api.get_user(user_id=user)
                elif isinstance(user, str):
                    user_obj = twitter.api.get_user(screen_name=user)
            except tweepy.error.TweepError:
                queue.task_done()
                continue
            if not _is_eligible(user_obj):
                print(FOLLOW_UNELIGIBLE.format(left=queue.qsize() + 1,
                                               screen_name=user, id=user))
                queue.task_done()
                continue

            while True:
                try:
                    if isinstance(user, int):
                        twitter.api.create_friendship(user_id=user)
                    elif isinstance(user, str):
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
    """Massively unfollow users.

    Args:
        only_followers: only unfollow users who already follow you.
        only_unfollowers: only unfollow users who don't follow you.
        num_threads: number of threads that will be launched to unfollow users
            in parallel.

    """
    if only_followers and only_unfollowers:
        raise ValueError('choose either only_followers or only_unfollowers!')

    users = []
    all_users = []
    total = twitter.me.friends_count
    count = 100 if only_followers or only_unfollowers else 200
    for page in tweepy.Cursor(twitter.api.friends, count=count).pages():
        all_users.extend(page)
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

        print(STATUS_INFO.format(users=len(users),
                                 tpc=len(all_users) / total,
                                 fpc=len(users) / len(all_users)))
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
    """Print a list of users.

    Args:
        screen_name: screen name of the user we'll get the list from. can be
            omitted, and then it defaults to yourself.
        type: list of users that we'll download from screen_name: can be either
            his 'followers' or his 'friends' (following).
        format: can be either 'simple' (a list of screen names will be printed)
            or 'csv' (a csv file with screen_name, number of friends and number
            of followers will be printed).

    """
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
        print('user,friends,followers,lang')
    for page in tweepy.Cursor(func, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            if format == 'simple':
                print(user.screen_name)
            elif format == 'csv':
                print('%s,%d,%d,%s' % (user.screen_name,
                                       user.friends_count,
                                       user.followers_count,
                                       user.lang))


def print_tweets(screen_name=None, include_retweets=False):
    """Print a list of recent tweets.

    Args:
        screen_name: screen name of the user we'll get the list from. can be
            omitted, and then it defaults to yourself.
        include_retweets: whether retweets will be included in the list.

    """
    screen_name = screen_name or twitter.me.screen_name

    for status in tweepy.Cursor(twitter.api.user_timeline,
                                screen_name=screen_name).items():
        if not include_retweets and hasattr(status, 'retweeted_status'):
            continue
        text = status.text.replace('\n', ' ').replace('\r', ' ')
        print(text)


# from akari
def _is_eligible(user):
    """checks if a user is eligible to be followed."""
    if user.friends_count > 5000:
        return False
    if (user.followers_count > 5000 and
            user.friends_count / user.followers_count > 0.7):
        return False
    return True
