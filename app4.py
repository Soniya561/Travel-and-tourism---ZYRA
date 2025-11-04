from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import os
import secrets
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# MongoDB setup
try:
    mongo_uri = os.getenv("MONGO_URI")
    if mongo_uri and mongo_uri != "mongodb+srv://<username>:<password>@cluster0.mongodb.net/?retryWrites=true&w=majority":
        # Add SSL certificate verification bypass for development
        # Try with SSL first, then fallback to no SSL if needed
        try:
            client = MongoClient(
                mongo_uri,
                tls=True,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            # Test connection
            client.admin.command('ping')
            db = client.get_database("ai_chatbot_ccp")
            user_collection = db["users"]
            reset_tokens_collection = db["reset_tokens"]
            print("✅ Connected to MongoDB successfully with SSL")
        except Exception as ssl_error:
            print(f"⚠️ SSL connection failed: {ssl_error}")
            print("⚠️ Trying without SSL...")
            # Try without SSL
            client = MongoClient(
                mongo_uri,
                tls=False,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000
            )
            client.admin.command('ping')
            db = client.get_database("ai_chatbot_ccp")
            user_collection = db["users"]
            reset_tokens_collection = db["reset_tokens"]
            print("✅ Connected to MongoDB successfully without SSL")
    else:
        # Use in-memory storage for testing
        print("⚠️ Warning: Using in-memory storage. Set MONGO_URI in .env for persistent storage.")
        user_collection = None
        reset_tokens_collection = None
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    print("⚠️ Using in-memory storage for testing.")
    user_collection = None
    reset_tokens_collection = None

# In-memory storage for testing
_users_memory = []
_reset_tokens_memory = []

# Initialize test user
def init_test_user():
    """Initialize a test user for demo purposes"""
    test_user = {
        'name': 'Test User',
        'email': 'test@test.com',
        'username': 'user',
        'password': generate_password_hash('123'),
        'oauth_provider': None,
        'oauth_id': None,
        'created_at': datetime.datetime.utcnow()
    }
    
    if user_collection is not None:
        # Check if test user already exists
        existing_user = user_collection.find_one({"$or": [{"username": "user"}, {"email": "test@test.com"}]})
        if not existing_user:
            user_collection.insert_one(test_user)
            print("Test user created: username='user', password='123'")
    else:
        # In-memory storage
        existing_user = None
        for user in _users_memory:
            if user.get("username") == "user" or user.get("email") == "test@test.com":
                existing_user = user
                break
        
        if not existing_user:
            test_user["_id"] = len(_users_memory) + 1
            _users_memory.append(test_user)
            print("Test user created: username='user', password='123'")

# Initialize test user on module load
init_test_user()

class User:
    @staticmethod
    def find_by_email(email):
        if user_collection is not None:
            return user_collection.find_one({"email": email})
        else:
            # In-memory search
            for user in _users_memory:
                if user.get("email") == email:
                    return user
            return None

    @staticmethod
    def find_by_username(username):
        if user_collection is not None:
            return user_collection.find_one({"username": username})
        else:
            # In-memory search
            for user in _users_memory:
                if user.get("username") == username:
                    return user
            return None

    @staticmethod
    def find_by_email_or_username(identifier):
        """Find user by email or username"""
        if user_collection is not None:
            return user_collection.find_one({
                "$or": [
                    {"email": identifier},
                    {"username": identifier}
                ]
            })
        else:
            # In-memory search
            for user in _users_memory:
                if user.get("email") == identifier or user.get("username") == identifier:
                    return user
            return None

    @staticmethod
    def find_by_id(user_id):
        if user_collection is not None:
            try:
                return user_collection.find_one({"_id": ObjectId(user_id)})
            except:
                return None
        else:
            # In-memory search
            for user in _users_memory:
                if str(user.get("_id")) == str(user_id):
                    return user
            return None

    @staticmethod
    def find_by_oauth(provider, oauth_id):
        """Find user by OAuth provider and ID"""
        if user_collection is not None:
            return user_collection.find_one({
                "oauth_provider": provider,
                "oauth_id": oauth_id
            })
        else:
            # In-memory search
            for user in _users_memory:
                if user.get("oauth_provider") == provider and user.get("oauth_id") == oauth_id:
                    return user
            return None

    @staticmethod
    def create_user(user_data):
        # Add creation timestamp and default OAuth fields
        user_data['created_at'] = datetime.datetime.utcnow()
        if 'oauth_provider' not in user_data:
            user_data['oauth_provider'] = None
        if 'oauth_id' not in user_data:
            user_data['oauth_id'] = None

        if User.find_by_email(user_data['email']):
            return None  # User already exists

        if user_collection is not None:
            result = user_collection.insert_one(user_data)
            return result.inserted_id
        else:
            # In-memory storage
            user_id = len(_users_memory) + 1
            user_data["_id"] = user_id
            _users_memory.append(user_data)
            return user_id

    @staticmethod
    def verify_user(identifier, password):
        """Verify user by email/username and password"""
        user = User.find_by_email_or_username(identifier)
        if user and user.get("password") and check_password_hash(user["password"], password):
            return user
        return None

    @staticmethod
    def update_user(user_id, update_data):
        """Update user data"""
        if user_collection is not None:
            try:
                result = user_collection.update_one(
                    {"_id": ObjectId(user_id)},
                    {"$set": update_data}
                )
                return result.modified_count > 0
            except:
                return False
        else:
            # In-memory update
            for i, user in enumerate(_users_memory):
                if str(user.get("_id")) == str(user_id):
                    _users_memory[i].update(update_data)
                    return True
            return False

    @staticmethod
    def create_password_reset_token(email):
        """Create a password reset token"""
        user = User.find_by_email(email)
        if not user:
            return None
            
        token = secrets.token_urlsafe(32)
        expiry = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(os.getenv('RESET_TOKEN_EXPIRY', 3600)))
        
        token_data = {
            'token': token,
            'email': email,
            'user_id': str(user['_id']),
            'expiry': expiry,
            'used': False
        }
        
        if reset_tokens_collection is not None:
            # Remove existing tokens for this user
            reset_tokens_collection.delete_many({"email": email})
            reset_tokens_collection.insert_one(token_data)
        else:
            # In-memory storage
            # Remove existing tokens for this user
            _reset_tokens_memory[:] = [t for t in _reset_tokens_memory if t['email'] != email]
            token_data['_id'] = len(_reset_tokens_memory) + 1
            _reset_tokens_memory.append(token_data)
            
        return token

    @staticmethod
    def verify_reset_token(token):
        """Verify password reset token"""
        if reset_tokens_collection is not None:
            token_doc = reset_tokens_collection.find_one({
                "token": token,
                "used": False,
                "expiry": {"$gt": datetime.datetime.utcnow()}
            })
        else:
            # In-memory search
            token_doc = None
            for t in _reset_tokens_memory:
                if (t['token'] == token and 
                    not t['used'] and 
                    t['expiry'] > datetime.datetime.utcnow()):
                    token_doc = t
                    break
                    
        return token_doc

    @staticmethod
    def use_reset_token(token, new_password):
        """Use password reset token to change password"""
        token_doc = User.verify_reset_token(token)
        if not token_doc:
            return False
            
        # Update password
        hashed_password = generate_password_hash(new_password)
        user_updated = User.update_user(token_doc['user_id'], {'password': hashed_password})
        
        if user_updated:
            # Mark token as used
            if reset_tokens_collection is not None:
                reset_tokens_collection.update_one(
                    {"token": token},
                    {"$set": {"used": True}}
                )
            else:
                # In-memory update
                for t in _reset_tokens_memory:
                    if t['token'] == token:
                        t['used'] = True
                        break
            return True
            