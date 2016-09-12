from datetime import datetime, timedelta
from queue import Queue
import threading

import tweepy

from twitter import twitter


class Parallel(object):
    def __init__(self, func, things, num_threads=50):
        self.queue = Queue()
        for i in range(num_threads):
            thread = threading.Thread(target=func, args=(self.queue,))
            thread.daemon = True
            thread.start()

        for thing in things:
            self.queue.put(thing)

    def start(self):
        self.queue.join()


def follow_followers(screen_name=None, num_threads=50):
    screen_name = screen_name or twitter.me.screen_name

    # download the list of users to follow
    users = []
    for page in tweepy.Cursor(twitter.api.followers, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            if (not user.following and
                not user.follow_request_sent and
                user.id != twitter.me.id and
                user.followers_count > 50 and
                (hasattr(user, 'status') and
                 user.status.created_at > datetime.now() - timedelta(days=7))):
                users.append(user)
        print('{len} users downloaded...'.format(len=len(users)))
    print('Finished: {len} users total'.format(len=len(users)))

    def follow(queue):
        while True:
            user = queue.get()
            while True:
                try:
                    user.follow()
                except tweepy.error.TweepError as e:
                    print('Following @{screen_name} ({id}): error: {e}'
                          .format(screen_name=user.screen_name,
                                  id=user.id,
                                  e=str(e)))
                else:
                    print('Following @{screen_name} ({id}): success!'
                          .format(screen_name=user.screen_name,
                                  id=user.id))
                    break
            queue.task_done()

    parallel = Parallel(follow, users)
    parallel.start()


def mass_unfollow(only_unfollowers=False):
    users = []
    count = 100 if only_unfollowers else 200
    for page in tweepy.Cursor(twitter.api.friends, count=count).pages():
        if only_unfollowers:
            user_ids = [user.id for user in page]
            for user in twitter.api._lookup_friendships(user_ids):
                if not user.is_followed_by:
                    users.append(user)
        else:
            users.extend([user.screen_name for user in page])

        print('{len} users downloaded...'.format(len=len(users)))
    print('Finished: {len} users total'.format(len=len(users)))

    def unfollow(queue):
        while True:
            user = queue.get()
            print('Unfollowing @{screen_name} ({id})'
                  .format(screen_name=user.screen_name,
                          id=user.id))
            try:
                twitter.api.destroy_friendship(user.id)
            except tweepy.error.TweepError as e:
                print('Error unfollowing.')
            queue.task_done()

    parallel = Parallel(unfollow, users)
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
