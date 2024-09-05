from pymongo import MongoClient

client = MongoClient('mongodb://localhost:27017/')

# Creating DB
db = client['light_tracker_db']

# Creating collections
subscriptions_collection = db['subscriptions']
outage_groups_collection = db['outage_groups']
user_notifications_collection = db['user_notifications']

