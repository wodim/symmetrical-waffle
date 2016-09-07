import tweepy

from twitter import twitter


def follow_followers(screen_name=None):
    screen_name = screen_name or twitter.me.screen_name
    for page in tweepy.Cursor(twitter.api.followers, screen_name=screen_name,
                              count=200).pages():
        for user in page:
            if (not user.following and
                not user.follow_request_sent and
                user.id != twitter.me.id and
                user.followers_count > 100):
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


def unfollow_my_unfollowers():
    # 100 per page is the max lookup_friendships can do
    for page in tweepy.Cursor(twitter.api.friends, count=100).pages():
        user_ids = [user.id for user in page]
        for user in twitter.api._lookup_friendships(user_ids):
            if not user.is_followed_by:
                print('Unfollowing @{screen_name} ({id})'
                      .format(screen_name=user.screen_name,
                              id=user.id))
                try:
                    twitter.api.destroy_friendship(user.id)
                except tweepy.error.TweepError as e:
                    print('Error unfollowing.')


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
