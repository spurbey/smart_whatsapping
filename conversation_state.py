# conversation_state.py - Manages conversation state using Redis

import uuid
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from redis_manager import RedisManager

logger = logging.getLogger(__name__)

class ConversationState:
    """
    Manages conversation state for individual customers
    Handles state creation, updates, and lifecycle management
    """
    
    def __init__(self, redis_manager: RedisManager, session_timeout: int = 1800):
        """
        Initialize conversation state manager
        
        Args:
            redis_manager: Redis connection manager
            session_timeout: Session timeout in seconds (default: 30 minutes)
        """
        self.redis = redis_manager
        self.session_timeout = session_timeout
    
    def get_conversation_key(self, customer_id: str) -> str:
        """
        Generate Redis key for customer conversation
        
        Args:
            customer_id: Unique customer identifier
            
        Returns:
            str: Redis key (e.g., "conversation:cust_123")
        """
        return f"conversation:{customer_id}"
    
    def create_new_session(self, customer_id: str) -> Dict[str, Any]:
        """
        Create new conversation session for customer
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict: New conversation state
        """
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        
        new_state = {
            "customer_id": customer_id,
            "session_id": session_id,
            "current_flow": None,           # No active flow initially
            "current_step": None,           # No active step
            "collected_data": {},           # Data collected during flow
            "flow_history": [],             # Track completed flows
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "message_count": 0,
                "total_flows_started": 0,
                "total_flows_completed": 0
            }
        }
        
        # Store in Redis
        key = self.get_conversation_key(customer_id)
        success = self.redis.set_data(key, new_state, self.session_timeout)
        
        if success:
            logger.info(f"Created new conversation session: {customer_id} -> {session_id}")
        else:
            logger.error(f"Failed to create conversation session for {customer_id}")
        
        return new_state
    
    def get_state(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current conversation state for customer
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict: Current state or None if no active session
        """
        key = self.get_conversation_key(customer_id)
        state = self.redis.get_data(key)
        
        if state:
            # Update last activity time
            state["metadata"]["last_activity"] = datetime.now().isoformat()
            # Save updated state back to Redis
            self.redis.set_data(key, state, self.session_timeout)
            logger.debug(f"Retrieved conversation state for {customer_id}")
        else:
            logger.debug(f"No active conversation state for {customer_id}")
        
        return state
    
    def update_state(self, customer_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update conversation state for customer
        
        Args:
            customer_id: Customer identifier
            updates: Dictionary of updates to apply
            
        Returns:
            bool: True if updated successfully
        """
        key = self.get_conversation_key(customer_id)
        current_state = self.redis.get_data(key)
        
        if not current_state:
            logger.warning(f"Cannot update state - no active session for {customer_id}")
            return False
        
        # Apply updates
        for key_path, value in updates.items():
            if "." in key_path:
                # Handle nested keys like "metadata.message_count"
                parts = key_path.split(".")
                target = current_state
                for part in parts[:-1]:
                    if part not in target:
                        target[part] = {}
                    target = target[part]
                target[parts[-1]] = value
            else:
                # Handle top-level keys
                current_state[key_path] = value
        
        # Always update last activity
        current_state["metadata"]["last_activity"] = datetime.now().isoformat()
        
        # Save back to Redis
        redis_key = self.get_conversation_key(customer_id)
        success = self.redis.set_data(redis_key, current_state, self.session_timeout)
        
        if success:
            logger.debug(f"Updated conversation state for {customer_id}")
        else:
            logger.error(f"Failed to update conversation state for {customer_id}")
        
        return success
    
    def start_flow(self, customer_id: str, flow_name: str) -> bool:
        """
        Start a new conversation flow
        
        Args:
            customer_id: Customer identifier
            flow_name: Name of flow to start (e.g., "support", "product_search")
            
        Returns:
            bool: True if flow started successfully
        """
        updates = {
            "current_flow": flow_name,
            "current_step": "flow_started",
            "collected_data": {},  # Reset data for new flow
            "metadata.total_flows_started": None  # Will be incremented below
        }
        
        # Get current state to increment counter
        current_state = self.get_state(customer_id)
        if current_state:
            updates["metadata.total_flows_started"] = current_state["metadata"]["total_flows_started"] + 1
        else:
            # Create new session if none exists
            self.create_new_session(customer_id)
            updates["metadata.total_flows_started"] = 1
        
        success = self.update_state(customer_id, updates)
        
        if success:
            logger.info(f"Started flow '{flow_name}' for customer {customer_id}")
        
        return success
    
    def complete_flow(self, customer_id: str, outcome: str = "completed") -> bool:
        """
        Mark current flow as completed
        
        Args:
            customer_id: Customer identifier
            outcome: Flow outcome ("completed", "abandoned", "escalated")
            
        Returns:
            bool: True if flow completed successfully
        """
        current_state = self.get_state(customer_id)
        if not current_state or not current_state.get("current_flow"):
            logger.warning(f"Cannot complete flow - no active flow for {customer_id}")
            return False
        
        # Add to flow history
        flow_record = {
            "flow": current_state["current_flow"],
            "outcome": outcome,
            "completed_at": datetime.now().isoformat(),
            "data_collected": current_state["collected_data"].copy()
        }
        
        flow_history = current_state.get("flow_history", [])
        flow_history.append(flow_record)
        
        updates = {
            "current_flow": None,
            "current_step": None,
            "collected_data": {},
            "flow_history": flow_history,
            "metadata.total_flows_completed": current_state["metadata"]["total_flows_completed"] + 1
        }
        
        success = self.update_state(customer_id, updates)
        
        if success:
            logger.info(f"Completed flow for customer {customer_id} with outcome: {outcome}")
        
        return success
    
    def clear_session(self, customer_id: str) -> bool:
        """
        Clear conversation session (delete from Redis)
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            bool: True if cleared successfully
        """
        key = self.get_conversation_key(customer_id)
        success = self.redis.delete_data(key)
        
        if success:
            logger.info(f"Cleared conversation session for {customer_id}")
        
        return success
    
    def has_active_session(self, customer_id: str) -> bool:
        """
        Check if customer has active conversation session
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            bool: True if active session exists
        """
        key = self.get_conversation_key(customer_id)
        return self.redis.get_data(key) is not None
    
    def get_or_create_state(self, customer_id: str) -> Dict[str, Any]:
        """
        Get existing state or create new session if none exists
        
        Args:
            customer_id: Customer identifier
            
        Returns:
            Dict: Conversation state (existing or newly created)
        """
        state = self.get_state(customer_id)
        
        if state is None:
            state = self.create_new_session(customer_id)
        
        return state

# Test function for conversation state
def test_conversation_state():
    """
    Test conversation state operations
    """
    print("🧪 Testing Conversation State Manager...")
    
    # Initialize Redis manager
    redis_mgr = RedisManager()
    if not redis_mgr.connect():
        print("❌ Redis not available for testing")
        return False
    
    # Initialize conversation state manager
    conv_state = ConversationState(redis_mgr)
    test_customer_id = "test_customer_123"
    
    # Clean up any existing test data
    conv_state.clear_session(test_customer_id)
    
    print("1. Testing session creation...")
    state = conv_state.create_new_session(test_customer_id)
    if state and state["customer_id"] == test_customer_id:
        print("✅ Session created successfully")
        print(f"   Session ID: {state['session_id']}")
    else:
        print("❌ Session creation failed")
        return False
    
    print("2. Testing state retrieval...")
    retrieved_state = conv_state.get_state(test_customer_id)
    if retrieved_state and retrieved_state["session_id"] == state["session_id"]:
        print("✅ State retrieval successful")
    else:
        print("❌ State retrieval failed")
        return False
    
    print("3. Testing flow start...")
    if conv_state.start_flow(test_customer_id, "support"):
        print("✅ Flow started successfully")
        
        # Verify flow was started
        updated_state = conv_state.get_state(test_customer_id)
        if updated_state["current_flow"] == "support":
            print("   Flow correctly set to 'support'")
        else:
            print("❌ Flow not correctly set")
    else:
        print("❌ Flow start failed")
    
    print("4. Testing state updates...")
    if conv_state.update_state(test_customer_id, {
        "current_step": "issue_type",
        "collected_data": {"issue": "order_problem"},
        "metadata.message_count": 3
    }):
        print("✅ State update successful")
        
        # Verify updates
        updated_state = conv_state.get_state(test_customer_id)
        if (updated_state["current_step"] == "issue_type" and 
            updated_state["collected_data"]["issue"] == "order_problem" and
            updated_state["metadata"]["message_count"] == 3):
            print("   All updates applied correctly")
        else:
            print("❌ Updates not applied correctly")
    else:
        print("❌ State update failed")
    
    print("5. Testing flow completion...")
    if conv_state.complete_flow(test_customer_id, "completed"):
        print("✅ Flow completion successful")
        
        # Verify flow was completed
        final_state = conv_state.get_state(test_customer_id)
        if (final_state["current_flow"] is None and 
            len(final_state["flow_history"]) == 1 and
            final_state["flow_history"][0]["outcome"] == "completed"):
            print("   Flow correctly completed and logged")
        else:
            print("❌ Flow completion not correctly recorded")
    else:
        print("❌ Flow completion failed")
    
    print("6. Testing session cleanup...")
    if conv_state.clear_session(test_customer_id):
        print("✅ Session cleared successfully")
        
        # Verify session was cleared
        if not conv_state.has_active_session(test_customer_id):
            print("   Session successfully removed")
        else:
            print("❌ Session still exists after clearing")
    else:
        print("❌ Session clear failed")
    
    print("🎉 All conversation state tests completed!")
    return True

if __name__ == "__main__":
    test_conversation_state()