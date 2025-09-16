# redis_manager.py - Basic Redis operations for conversation state

import redis
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class RedisManager:
    """
    Basic Redis connection and operations for conversation state
    Handles connection, basic get/set, and error handling
    """
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0):
        """
        Initialize Redis connection
        
        Args:
            host: Redis server host
            port: Redis server port  
            db: Redis database number
        """
        self.host = host
        self.port = port
        self.db = db
        self.client = None
        self.is_connected = False
    
    def connect(self) -> bool:
        """
        Establish connection to Redis server
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        try:
            self.client = redis.Redis(
                host=self.host, 
                port=self.port, 
                db=self.db,
                decode_responses=True  # Automatically decode bytes to strings
            )
            
            # Test connection
            self.client.ping()
            self.is_connected = True
            logger.info(f"✅ Redis connected: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            self.is_connected = False
            return False
    
    def set_data(self, key: str, data: Dict[str, Any], ttl: int = 1800) -> bool:
        """
        Store data in Redis with TTL (Time To Live)
        
        Args:
            key: Redis key (e.g., "conversation:customer_123")
            data: Dictionary to store as JSON
            ttl: Expiration time in seconds (default: 30 minutes)
            
        Returns:
            bool: True if stored successfully, False otherwise
        """
        if not self.is_connected:
            logger.warning("Redis not connected, cannot store data")
            return False
        
        try:
            # Convert dict to JSON string
            json_data = json.dumps(data, default=str)  # default=str handles datetime objects
            
            # Store with TTL
            result = self.client.setex(key, ttl, json_data)
            logger.debug(f"Stored data in Redis: {key} (TTL: {ttl}s)")
            return result
            
        except Exception as e:
            logger.error(f"Error storing data in Redis: {e}")
            return False
    
    def get_data(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve data from Redis
        
        Args:
            key: Redis key to retrieve
            
        Returns:
            Dict if found, None if not found or error
        """
        if not self.is_connected:
            logger.warning("Redis not connected, cannot retrieve data")
            return None
        
        try:
            json_data = self.client.get(key)
            
            if json_data is None:
                logger.debug(f"No data found for key: {key}")
                return None
            
            # Convert JSON string back to dict
            data = json.loads(json_data)
            logger.debug(f"Retrieved data from Redis: {key}")
            return data
            
        except Exception as e:
            logger.error(f"Error retrieving data from Redis: {e}")
            return None
    
    def delete_data(self, key: str) -> bool:
        """
        Delete data from Redis
        
        Args:
            key: Redis key to delete
            
        Returns:
            bool: True if deleted, False otherwise
        """
        if not self.is_connected:
            return False
        
        try:
            result = self.client.delete(key)
            logger.debug(f"Deleted from Redis: {key}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error deleting from Redis: {e}")
            return False
    
    def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for a key
        
        Args:
            key: Redis key
            
        Returns:
            int: Remaining seconds (-1 if no expiry, -2 if key doesn't exist)
        """
        if not self.is_connected:
            return -2
        
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"Error getting TTL: {e}")
            return -2
    
    def ping(self) -> bool:
        """
        Test Redis connection
        
        Returns:
            bool: True if Redis is responding
        """
        if not self.client:
            return False
        
        try:
            self.client.ping()
            return True
        except Exception:
            return False

# Test function to verify Redis operations
def test_redis_manager():
    """
    Test function to verify Redis operations work correctly
    """
    print("🧪 Testing Redis Manager...")
    
    # Initialize Redis manager
    redis_mgr = RedisManager()
    
    # Test connection
    if not redis_mgr.connect():
        print("❌ Redis connection failed - make sure Redis server is running")
        return False
    
    # Test data operations
    test_key = "test:conversation:123"
    test_data = {
        "customer_id": "cust_123",
        "flow": "support",
        "step": "issue_type",
        "data": {"issue": "order_problem"},
        "created_at": datetime.now().isoformat()
    }
    
    # Test SET
    print("1. Testing SET operation...")
    if redis_mgr.set_data(test_key, test_data, ttl=60):
        print("✅ SET successful")
    else:
        print("❌ SET failed")
        return False
    
    # Test GET
    print("2. Testing GET operation...")
    retrieved_data = redis_mgr.get_data(test_key)
    if retrieved_data and retrieved_data["customer_id"] == "cust_123":
        print("✅ GET successful")
        print(f"   Retrieved: {retrieved_data}")
    else:
        print("❌ GET failed")
        return False
    
    # Test TTL
    print("3. Testing TTL...")
    ttl = redis_mgr.get_ttl(test_key)
    if ttl > 0:
        print(f"✅ TTL working: {ttl} seconds remaining")
    else:
        print("❌ TTL not working")
    
    # Test DELETE
    print("4. Testing DELETE operation...")
    if redis_mgr.delete_data(test_key):
        print("✅ DELETE successful")
        
        # Verify deletion
        if redis_mgr.get_data(test_key) is None:
            print("✅ Key successfully deleted")
        else:
            print("❌ Key still exists after deletion")
    else:
        print("❌ DELETE failed")
    
    print("🎉 All Redis tests completed!")
    return True

if __name__ == "__main__":
    test_redis_manager()