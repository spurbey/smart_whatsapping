# support_flow.py - Customer support conversation flow

import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime
from conversation_state import ConversationState

logger = logging.getLogger(__name__)

class SupportFlow:
    """
    Handles customer support conversation flow
    Manages multi-step support interactions with state preservation
    """
    
    def __init__(self, conversation_manager: ConversationState):
        """
        Initialize support flow handler
        
        Args:
            conversation_manager: Conversation state manager
        """
        self.conv_mgr = conversation_manager
        self.flow_name = "support"
        
        # Define flow steps and their logic
        self.flow_steps = {
            "1_issue_type": {
                "prompt": "I'll help you with that! What type of issue are you having?",
                "options": [
                    "1. Order issue (delivery, tracking, etc.)",
                    "2. Product question (features, compatibility)", 
                    "3. Account problem (login, billing, etc.)",
                    "4. Return or refund request"
                ],
                "next_step": "2_collect_details"
            },
            "2_collect_details": {
                "prompt": "Tell me more about your {issue_type}. Please provide details:",
                "input_type": "text",
                "next_step": "3_gather_info"
            },
            "3_gather_info": {
                "prompt": "To help you better, I need some information:",
                "input_type": "text", 
                "next_step": "4_provide_solution"
            },
            "4_provide_solution": {
                "action": "generate_solution",
                "next_step": "5_confirmation"
            },
            "5_confirmation": {
                "prompt": "Did this help resolve your issue?",
                "options": [
                    "1. Yes, issue resolved!",
                    "2. No, I still need help"
                ],
                "next_step": "end"
            }
        }
    
    def start_support_flow(self, customer_id: str, initial_message: str) -> Tuple[str, Dict[str, Any]]:
        """
        Start support flow for customer
        
        Args:
            customer_id: Customer identifier
            initial_message: Initial message that triggered support
            
        Returns:
            Tuple[str, Dict]: (response_message, updated_state)
        """
        # Start the flow
        success = self.conv_mgr.start_flow(customer_id, self.flow_name)
        
        if not success:
            return "Sorry, I'm having trouble right now. Please try again.", {}
        
        # Set initial step and collect initial context
        updates = {
            "current_step": "1_issue_type",
            "collected_data": {
                "initial_message": initial_message,
                "started_at": datetime.now().isoformat()
            }
        }
        
        self.conv_mgr.update_state(customer_id, updates)
        
        # Generate first response
        step_config = self.flow_steps["1_issue_type"]
        response = self._generate_step_response(step_config)
        
        # Get updated state
        state = self.conv_mgr.get_state(customer_id)
        
        logger.info(f"Started support flow for customer {customer_id}")
        
        return response, state
    
    def process_support_message(self, customer_id: str, message: str) -> Tuple[str, Dict[str, Any]]:
        """
        Process message within support flow
        
        Args:
            customer_id: Customer identifier
            message: User's message
            
        Returns:
            Tuple[str, Dict]: (response_message, updated_state)
        """
        # Get current state
        state = self.conv_mgr.get_state(customer_id)
        
        if not state or state.get("current_flow") != self.flow_name:
            return "I don't have an active support session for you. How can I help?", {}
        
        current_step = state.get("current_step")
        
        if not current_step or current_step not in self.flow_steps:
            return "Something went wrong. Let me restart. How can I help you?", {}
        
        # Process current step
        try:
            if current_step == "1_issue_type":
                return self._handle_issue_type_selection(customer_id, message, state)
            elif current_step == "2_collect_details":
                return self._handle_detail_collection(customer_id, message, state)
            elif current_step == "3_gather_info":
                return self._handle_info_gathering(customer_id, message, state)
            elif current_step == "4_provide_solution":
                return self._handle_solution_provision(customer_id, message, state)
            elif current_step == "5_confirmation":
                return self._handle_confirmation(customer_id, message, state)
            else:
                return "I'm not sure what step we're on. Let me help you restart.", {}
                
        except Exception as e:
            logger.error(f"Error processing support message: {e}")
            return "I encountered an error. Let me try to help you again. What's your issue?", {}
    
    def _handle_issue_type_selection(self, customer_id: str, message: str, state: Dict) -> Tuple[str, Dict]:
        """Handle issue type selection step"""
        
        # Parse user selection
        issue_type = self._parse_issue_type(message)
        
        if not issue_type:
            # Invalid selection
            step_config = self.flow_steps["1_issue_type"]
            response = "Please select a valid option:\n\n" + self._generate_step_response(step_config)
            return response, state
        
        # Valid selection - move to next step
        updates = {
            "current_step": "2_collect_details",
            "collected_data.issue_type": issue_type,
            "metadata.message_count": state["metadata"]["message_count"] + 1
        }
        
        self.conv_mgr.update_state(customer_id, updates)
        
        # Generate response for detail collection
        if issue_type == "order_issue":
            response = "I'll help you with your order issue. Please tell me:\n• Your order number (if you have it)\n• What specifically is wrong\n• When you placed the order"
        elif issue_type == "product_question":
            response = "I'll help answer your product question. Please tell me:\n• Which product you're asking about\n• What you'd like to know"
        elif issue_type == "account_problem":
            response = "I'll help with your account issue. Please describe:\n• What problem you're experiencing\n• What you were trying to do"
        elif issue_type == "return_refund":
            response = "I'll help you with your return or refund. Please provide:\n• Your order number\n• Which item(s) you want to return\n• Reason for return"
        else:
            response = f"Tell me more about your {issue_type}. Please provide details:"
        
        updated_state = self.conv_mgr.get_state(customer_id)
        return response, updated_state
    
    def _handle_detail_collection(self, customer_id: str, message: str, state: Dict) -> Tuple[str, Dict]:
        """Handle detail collection step"""
        
        # Store the details provided
        updates = {
            "current_step": "3_gather_info", 
            "collected_data.problem_details": message,
            "metadata.message_count": state["metadata"]["message_count"] + 1
        }
        
        self.conv_mgr.update_state(customer_id, updates)
        
        # Determine what additional info we need based on issue type
        issue_type = state["collected_data"].get("issue_type", "")
        
        if issue_type == "order_issue":
            response = "Thank you for those details. To help you better, can you provide your email address or phone number associated with the order?"
        elif issue_type == "product_question":
            response = "Thanks for the details. Let me look up information about that product for you."
            # Skip info gathering for product questions
            updates["current_step"] = "4_provide_solution"
            self.conv_mgr.update_state(customer_id, updates)
            return self._handle_solution_provision(customer_id, message, self.conv_mgr.get_state(customer_id))
        elif issue_type == "account_problem":
            response = "I understand the issue. Can you confirm the email address associated with your account?"
        elif issue_type == "return_refund":
            response = "Got it. I'll help process your return. Can you confirm the email address you used for the order?"
        else:
            response = "Thank you for the information. Let me see how I can help you."
            # Move to solution step
            updates["current_step"] = "4_provide_solution"
            self.conv_mgr.update_state(customer_id, updates)
            return self._handle_solution_provision(customer_id, message, self.conv_mgr.get_state(customer_id))
        
        updated_state = self.conv_mgr.get_state(customer_id)
        return response, updated_state
    
    def _handle_info_gathering(self, customer_id: str, message: str, state: Dict) -> Tuple[str, Dict]:
        """Handle additional info gathering step"""
        
        # Store additional info and move to solution
        updates = {
            "current_step": "4_provide_solution",
            "collected_data.additional_info": message,
            "metadata.message_count": state["metadata"]["message_count"] + 1
        }
        
        self.conv_mgr.update_state(customer_id, updates)
        
        # Move to solution provision
        updated_state = self.conv_mgr.get_state(customer_id)
        return self._handle_solution_provision(customer_id, message, updated_state)
    
    def _handle_solution_provision(self, customer_id: str, message: str, state: Dict) -> Tuple[str, Dict]:
        """Handle solution provision step"""
        
        # Generate solution based on collected data
        collected_data = state.get("collected_data", {})
        issue_type = collected_data.get("issue_type", "")
        
        solution = self._generate_solution(issue_type, collected_data)
        
        # Move to confirmation step
        updates = {
            "current_step": "5_confirmation",
            "collected_data.solution_provided": solution,
            "metadata.message_count": state["metadata"]["message_count"] + 1
        }
        
        self.conv_mgr.update_state(customer_id, updates)
        
        # Format response with solution + confirmation prompt
        response = f"{solution}\n\n" + self.flow_steps["5_confirmation"]["prompt"] + "\n\n"
        for option in self.flow_steps["5_confirmation"]["options"]:
            response += f"{option}\n"
        
        updated_state = self.conv_mgr.get_state(customer_id)
        return response, updated_state
    
    def _handle_confirmation(self, customer_id: str, message: str, state: Dict) -> Tuple[str, Dict]:
        """Handle final confirmation step"""
        
        message_lower = message.lower().strip()
        
        if message_lower in ["1", "yes", "resolved", "fixed", "good"]:
            # Issue resolved
            outcome = "resolved"
            response = "Great! I'm glad I could help resolve your issue. 😊\n\nIs there anything else I can help you with today?"
        elif message_lower in ["2", "no", "not resolved", "still need help"]:
            # Issue not resolved - escalate
            outcome = "escalated"
            response = "I understand you still need help. Let me connect you with a human support agent who can assist you further.\n\nYour case has been escalated and someone will contact you within 24 hours."
        else:
            # Invalid response - ask for clarification
            response = "Please let me know if the solution helped:\n\n1. Yes, issue resolved!\n2. No, I still need help"
            return response, state
        
        # Complete the flow
        self.conv_mgr.complete_flow(customer_id, outcome)
        
        # Log completion
        logger.info(f"Support flow completed for customer {customer_id} with outcome: {outcome}")
        
        # Clear state since flow is complete
        final_state = self.conv_mgr.get_state(customer_id) or {}
        
        return response, final_state
    
    def _parse_issue_type(self, message: str) -> Optional[str]:
        """Parse user's issue type selection"""
        message_lower = message.lower().strip()
        
        if message_lower in ["1", "order", "order issue", "delivery", "tracking"]:
            return "order_issue"
        elif message_lower in ["2", "product", "product question", "features"]:
            return "product_question"
        elif message_lower in ["3", "account", "account problem", "login", "billing"]:
            return "account_problem"
        elif message_lower in ["4", "return", "refund", "return refund"]:
            return "return_refund"
        else:
            return None
    
    def _generate_step_response(self, step_config: Dict) -> str:
        """Generate response for a flow step"""
        response = step_config["prompt"]
        
        if "options" in step_config:
            response += "\n\n"
            for option in step_config["options"]:
                response += f"{option}\n"
        
        return response
    
    def _generate_solution(self, issue_type: str, collected_data: Dict) -> str:
        """Generate solution based on issue type and collected data"""
        
        if issue_type == "order_issue":
            return ("Here's how I can help with your order issue:\n\n"
                   "1. **Check Order Status**: I can look up your order using your email\n"
                   "2. **Tracking Information**: Most orders ship within 24-48 hours\n"
                   "3. **Delivery Issues**: If your order is delayed, I can check with our shipping partner\n\n"
                   "For immediate assistance, you can also track your order at: https://yourstore.com/track")
        
        elif issue_type == "product_question":
            return ("I'd be happy to help with product information:\n\n"
                   "1. **Product Details**: Check our website for full specifications\n"
                   "2. **Compatibility**: Most of our products work with standard systems\n"
                   "3. **Warranty**: All products come with 1-year manufacturer warranty\n\n"
                   "For detailed specs, visit: https://yourstore.com/products")
        
        elif issue_type == "account_problem":
            return ("Here are solutions for common account issues:\n\n"
                   "1. **Password Reset**: Use 'Forgot Password' on the login page\n"
                   "2. **Account Access**: Clear your browser cache and try again\n"
                   "3. **Billing Questions**: Check your email for receipt confirmations\n\n"
                   "Account help: https://yourstore.com/account-help")
        
        elif issue_type == "return_refund":
            return ("Here's our return and refund process:\n\n"
                   "1. **Return Window**: 30 days from purchase date\n"
                   "2. **Process**: Visit our returns page to start a return\n"
                   "3. **Refunds**: Processed within 5-7 business days after we receive the item\n\n"
                   "Start your return: https://yourstore.com/returns")
        
        else:
            return "I've noted your issue and our support team will help you resolve it."

# Test function for support flow
def test_support_flow():
    """
    Test support flow operations
    """
    print("🧪 Testing Support Flow...")
    
    # Initialize dependencies
    from redis_manager import RedisManager
    
    redis_mgr = RedisManager()
    if not redis_mgr.connect():
        print("❌ Redis not available for testing")
        return False
    
    conv_state = ConversationState(redis_mgr)
    support_flow = SupportFlow(conv_state)
    
    test_customer_id = "test_support_customer"
    
    # Clean up any existing test data
    conv_state.clear_session(test_customer_id)
    
    print("1. Testing flow start...")
    response, state = support_flow.start_support_flow(test_customer_id, "I have an issue with my order")
    if state and state.get("current_flow") == "support":
        print("✅ Support flow started successfully")
        print(f"   Response: {response[:100]}...")
    else:
        print("❌ Support flow start failed")
        return False
    
    print("2. Testing issue type selection...")
    response, state = support_flow.process_support_message(test_customer_id, "1")
    if state.get("current_step") == "2_collect_details":
        print("✅ Issue type selection processed")
        print(f"   Selected: {state['collected_data']['issue_type']}")
    else:
        print("❌ Issue type selection failed")
    
    print("3. Testing detail collection...")
    response, state = support_flow.process_support_message(test_customer_id, "My order #1234 hasn't arrived yet")
    if state.get("current_step") == "3_gather_info":
        print("✅ Detail collection processed")
        print(f"   Details: {state['collected_data']['problem_details'][:50]}...")
    else:
        print("❌ Detail collection failed")
    
    print("4. Testing info gathering...")
    response, state = support_flow.process_support_message(test_customer_id, "my email is test@example.com")
    if state.get("current_step") == "5_confirmation":
        print("✅ Info gathering processed")
        print(f"   Additional info: {state['collected_data']['additional_info']}")
    else:
        print("❌ Info gathering failed")
    
    print("5. Testing flow completion...")
    response, state = support_flow.process_support_message(test_customer_id, "1")
    if not conv_state.has_active_session(test_customer_id):
        print("✅ Flow completed and session cleared")
        print(f"   Final response: {response[:100]}...")
    else:
        print("❌ Flow completion failed")
    
    print("🎉 All support flow tests completed!")
    return True

if __name__ == "__main__":
    test_support_flow()