"""
Real WhatsApp Business API Integration using Twilio
"""

import os
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

class WhatsAppService:
    """
    Handles sending and receiving WhatsApp messages via Twilio
    """
    
    def __init__(self):
        # Get credentials from environment variables
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN') 
        self.whatsapp_number = os.getenv('TWILIO_WHATSAPP_NUMBER')
        
        if not all([self.account_sid, self.auth_token, self.whatsapp_number]):
            raise ValueError("Missing Twilio credentials in environment variables")
        
        # Initialize Twilio client
        self.client = Client(self.account_sid, self.auth_token)
        
        logger.info("✅ WhatsApp service initialized")
    
    def send_message(self, to_phone: str, message: str) -> Dict[str, Any]:
        """
        Send a WhatsApp message to a customer
        
        Args:
            to_phone: Customer's phone number (e.g., "+1234567890")
            message: Message text to send
            
        Returns:
            Dictionary with send status and message ID
        """
        try:
            # Format phone number for WhatsApp
            if not to_phone.startswith('whatsapp:'):
                to_phone = f"whatsapp:{to_phone}"
            
            # Send message via Twilio
            message_obj = self.client.messages.create(
                body=message,                      # Message content
                from_=self.whatsapp_number,       # Your Twilio WhatsApp number
                to=to_phone                       # Customer's WhatsApp number
            )
            
            logger.info(f"✅ WhatsApp message sent to {to_phone}: {message_obj.sid}")
            
            return {
                "status": "sent",
                "message_id": message_obj.sid,
                "to": to_phone,
                "content": message,
                "sent_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send WhatsApp message to {to_phone}: {e}")
            
            return {
                "status": "failed", 
                "error": str(e),
                "to": to_phone,
                "content": message
            }
    
    def process_incoming_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming WhatsApp webhook from Twilio
        
        Twilio sends webhooks when customers message you
        """
        try:
            # Extract data from Twilio webhook format
            from_number = webhook_data.get('From', '')  # "whatsapp:+1234567890"
            to_number = webhook_data.get('To', '')      # Your WhatsApp number  
            message_body = webhook_data.get('Body', '') # Message text
            message_sid = webhook_data.get('MessageSid', '') # Twilio message ID
            
            # Clean phone number (remove "whatsapp:" prefix)
            clean_phone = from_number.replace('whatsapp:', '') if from_number else ''
            
            logger.info(f"📱 Received WhatsApp message from {clean_phone}: {message_body}")
            
            return {
                "message_id": message_sid,
                "from_phone": clean_phone,
                "to_phone": to_number,
                "message_text": message_body,
                "timestamp": datetime.utcnow().isoformat(),
                "platform": "twilio_whatsapp",
                "raw_webhook": webhook_data
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to process WhatsApp webhook: {e}")
            raise e
    
    def generate_webhook_response(self, reply_message: str) -> str:
        """
        Generate TwiML response for immediate reply
        
        When Twilio sends you a webhook, you can immediately respond
        by returning TwiML (Twilio Markup Language)
        """
        try:
            response = MessagingResponse()
            response.message(reply_message)
            return str(response)
            
        except Exception as e:
            logger.error(f"❌ Failed to generate webhook response: {e}")
            return ""
        
    def send_interactive_buttons(self, to_phone: str, message: str, buttons: List[Dict]) -> Dict:
        """
        Send message with interactive buttons
        
        buttons = [
            {"id": "yes", "title": "Yes, please!"},
            {"id": "no", "title": "No, thanks"}
        ]
        """
        try:
            if not to_phone.startswith('whatsapp:'):
                to_phone = f"whatsapp:{to_phone}"
            
            # For Twilio sandbox, we'll simulate buttons with numbered options
            button_text = "\n\n" + "\n".join([f"{i+1}. {btn['title']}" for i, btn in enumerate(buttons)])
            full_message = message + button_text + "\n\nReply with the number of your choice."
            
            message_obj = self.client.messages.create(
                body=full_message,
                from_=self.whatsapp_number,
                to=to_phone
            )
            
            logger.info(f"✅ Interactive message sent to {to_phone}")
            
            return {
                "status": "sent",
                "message_id": message_obj.sid,
                "message_type": "interactive_buttons",
                "buttons": buttons
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send interactive message: {e}")
            return {"status": "failed", "error": str(e)}
        
    def send_menu_message(self, to_phone: str, title: str, menu_items: List[Dict]) -> Dict:
        """
        Send menu with multiple options
        
        menu_items = [
            {"id": "orders", "title": "📦 My Orders", "description": "Check order status"},
            {"id": "products", "title": "🛍️ Products", "description": "Browse our catalog"},
            {"id": "support", "title": "🆘 Support", "description": "Get help"}
        ]
        """
        try:
            if not to_phone.startswith('whatsapp:'):
                to_phone = f"whatsapp:{to_phone}"
            
            menu_text = f"*{title}*\n\n"
            for i, item in enumerate(menu_items):
                menu_text += f"{i+1}. {item['title']}\n   {item['description']}\n\n"
            
            menu_text += "Reply with the number of your choice."
            
            message_obj = self.client.messages.create(
                body=menu_text,
                from_=self.whatsapp_number,
                to=to_phone
            )
            
            return {
                "status": "sent",
                "message_id": message_obj.sid,
                "message_type": "menu",
                "menu_items": menu_items
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to send menu: {e}")
            return {"status": "failed", "error": str(e)}
        
    def broadcast_message(self, phone_list: List[str], message: str) -> Dict:
        """
        Send same message to multiple customers
        """
        results = {"successful": [], "failed": []}
        
        for phone in phone_list:
            try:
                result = self.send_message(phone, message)
                if result['status'] == 'sent':
                    results["successful"].append(phone)
                else:
                    results["failed"].append({"phone": phone, "error": result.get('error')})
            except Exception as e:
                results["failed"].append({"phone": phone, "error": str(e)})
        
        logger.info(f"📡 Broadcast sent: {len(results['successful'])} successful, {len(results['failed'])} failed")
        
        return {
            "status": "completed",
            "total_sent": len(phone_list),
            "successful": len(results["successful"]),
            "failed": len(results["failed"]),
            "results": results
        }
    

# Test function
def test_whatsapp_service():
    """
    Test WhatsApp service connectivity
    """
    try:
        service = WhatsAppService()
        
        # Try to send a test message to yourself
        # Replace with your WhatsApp number (the one you connected to sandbox)
        test_phone = "+1234567890"  # Your phone number
        
        result = service.send_message(
            test_phone, 
            "🤖 Test message from your automation system! If you received this, WhatsApp integration is working!"
        )
        
        print("WhatsApp Test Result:")
        print(f"Status: {result['status']}")
        if result['status'] == 'sent':
            print(f"Message ID: {result['message_id']}")
            print("✅ WhatsApp integration working!")
        else:
            print(f"Error: {result['error']}")
            print("❌ WhatsApp integration failed")
            
    except Exception as e:
        print(f"❌ WhatsApp test failed: {e}")

if __name__ == "__main__":
    test_whatsapp_service()

