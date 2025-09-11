# campaign_engine.py - New file for campaign logic

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
import json
import random
import string
from database import (
    Customer, CartItem, Campaign, CampaignSend, OfferCode,
    Product, Message, get_database_session
)
from whatsapp_integration import WhatsAppService
import logging

logger = logging.getLogger(__name__)

class CampaignEngine:
    """
    Handles automated marketing campaigns for cart abandonment, upselling, etc.
    """
    
    def __init__(self, whatsapp_service: WhatsAppService):
        self.whatsapp_service = whatsapp_service
    
    def generate_offer_code(self, campaign_name: str, offer_value: float) -> str:
        """Generate unique offer code like CART10OFF"""
        prefix = "CART"
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"{prefix}{int(offer_value)}{suffix}"
    
    def create_cart_abandonment_campaigns(self, db: Session) -> List[str]:
        """
        Create default cart abandonment campaigns
        """
        campaigns = [
            {
                "name": "Cart Reminder - 1 Hour",
                "campaign_type": "cart_abandonment",
                "trigger_delay_minutes": 60,
                "message_template": "Hey {customer_name}! 👋\n\nYou left something amazing in your cart:\n\n🛍️ {product_list}\n\nDon't miss out! Complete your order now and get FREE shipping! 🚚\n\nShop now: {cart_link}",
                "offer_type": "free_shipping",
                "offer_value": 0,
                "max_sends_per_customer": 1
            },
            {
                "name": "Cart Discount - 4 Hours", 
                "campaign_type": "cart_abandonment",
                "trigger_delay_minutes": 240,
                "message_template": "🎉 Special offer just for you, {customer_name}!\n\nYour cart is waiting:\n{product_list}\n\n💥 Get 10% OFF with code: {offer_code}\n⏰ Valid for next 24 hours only!\n\nClaim discount: {cart_link}",
                "offer_type": "percentage",
                "offer_value": 10,
                "max_sends_per_customer": 1
            },
            {
                "name": "Last Chance - 24 Hours",
                "campaign_type": "cart_abandonment", 
                "trigger_delay_minutes": 1440,
                "message_template": "⚠️ LAST CHANCE, {customer_name}!\n\nYour cart expires soon:\n{product_list}\n\n🔥 Final offer: 15% OFF + FREE shipping!\nCode: {offer_code}\n\n⏰ Only 2 hours left!\n\nSave now: {cart_link}",
                "offer_type": "percentage",
                "offer_value": 15,
                "max_sends_per_customer": 1
            }
        ]
        
        created_campaigns = []
        for campaign_data in campaigns:
            # Check if campaign already exists
            existing = db.query(Campaign).filter(
                Campaign.name == campaign_data["name"]
            ).first()
            
            if not existing:
                campaign = Campaign(**campaign_data)
                db.add(campaign)
                created_campaigns.append(campaign_data["name"])
        
        db.commit()
        logger.info(f"✅ Created {len(created_campaigns)} cart abandonment campaigns")
        return created_campaigns
    
    def find_abandoned_carts_for_campaigns(self, db: Session) -> List[Dict]:
        """
        Find abandoned carts that are ready for campaign messages
        """
        now = datetime.utcnow()
        ready_carts = []
        
        # Get all active campaigns
        campaigns = db.query(Campaign).filter(
            Campaign.is_active == True,
            Campaign.campaign_type == "cart_abandonment"
        ).all()
        
        for campaign in campaigns:
            # Calculate when carts should trigger this campaign
            trigger_time = now - timedelta(minutes=campaign.trigger_delay_minutes)
            
            # Find carts added around the trigger time (±5 minutes window)
            window_start = trigger_time - timedelta(minutes=5)
            window_end = trigger_time + timedelta(minutes=5)
            
            abandoned_carts = db.query(CartItem).filter(
                CartItem.added_at >= window_start,
                CartItem.added_at <= window_end,
                CartItem.is_recovered == False
            ).all()
            
            for cart in abandoned_carts:
                # Check if we already sent this campaign to this customer
                existing_send = db.query(CampaignSend).filter(
                    CampaignSend.campaign_id == campaign.id,
                    CampaignSend.customer_id == cart.customer_id,
                    CampaignSend.cart_item_id == cart.id
                ).first()
                
                if not existing_send and cart.campaign_sent_count < campaign.max_sends_per_customer:
                    ready_carts.append({
                        "cart": cart,
                        "campaign": campaign,
                        "customer": cart.customer,
                        "product": cart.product
                    })
        
        return ready_carts
    
    def personalize_message(self, template: str, customer: Customer, cart: CartItem, 
                          product: Product, offer_code: str = None) -> str:
        """
        Personalize campaign message template with customer data
        """
        customer_name = customer.first_name or "there"
        
        # Create product list text
        product_list = f"• {product.name} (${product.price})"
        if cart.quantity > 1:
            product_list += f" x{cart.quantity}"
        
        # Create cart link (placeholder for now)
        cart_link = f"https://yourstore.com/cart?recover={cart.id}"
        
        # Replace template variables
        message = template.replace("{customer_name}", customer_name)
        message = message.replace("{product_list}", product_list)
        message = message.replace("{cart_link}", cart_link)
        
        if offer_code:
            message = message.replace("{offer_code}", offer_code)
        
        return message
    
    def create_offer_code(self, db: Session, campaign: Campaign) -> Optional[str]:
        """
        Create unique offer code for campaign
        """
        if not campaign.offer_type or campaign.offer_type == "free_shipping":
            return None
        
        # Generate unique code
        code = self.generate_offer_code(campaign.name, campaign.offer_value)
        
        # Create offer code record
        offer = OfferCode(
            code=code,
            offer_type=campaign.offer_type,
            offer_value=campaign.offer_value,
            max_uses=1,  # Per customer
            expires_at=datetime.utcnow() + timedelta(hours=24),
            campaign_id=campaign.id
        )
        
        db.add(offer)
        db.commit()
        
        return code
    
    def send_campaign_message(self, db: Session, cart_data: Dict) -> Dict:
        """
        Send a single campaign message to customer
        """
        cart = cart_data["cart"]
        campaign = cart_data["campaign"]
        customer = cart_data["customer"]
        product = cart_data["product"]
        
        try:
            # Create offer code if needed
            offer_code = None
            if campaign.offer_type and campaign.offer_type != "free_shipping":
                offer_code = self.create_offer_code(db, campaign)
            
            # Personalize message
            message_content = self.personalize_message(
                campaign.message_template, customer, cart, product, offer_code
            )
            
            # Send WhatsApp message
            if customer.whatsapp_phone and self.whatsapp_service:
                whatsapp_result = self.whatsapp_service.send_message(
                    customer.whatsapp_phone, message_content
                )
                
                if whatsapp_result['status'] == 'sent':
                    # Create campaign send record
                    campaign_send = CampaignSend(
                        campaign_id=campaign.id,
                        customer_id=customer.id,
                        cart_item_id=cart.id,
                        message_content=message_content,
                        offer_code_used=offer_code,
                        whatsapp_message_id=whatsapp_result['message_id'],
                        sent_at=datetime.utcnow()
                    )
                    db.add(campaign_send)
                    
                    # Update cart tracking
                    cart.campaign_sent_count += 1
                    cart.last_campaign_sent = datetime.utcnow()
                    
                    # Save WhatsApp message to messages table
                    message_record = Message(
                        customer_id=customer.id,
                        channel="whatsapp",
                        direction="outbound",
                        content=message_content,
                        platform_message_id=whatsapp_result['message_id'],
                        sent_at=datetime.utcnow(),
                        bot_handled=True,
                        metadata_json=json.dumps({
                            "campaign_id": campaign.id,
                            "campaign_type": "cart_abandonment",
                            "offer_code": offer_code,
                            "cart_item_id": cart.id
                        })
                    )
                    db.add(message_record)
                    
                    db.commit()
                    
                    logger.info(f"✅ Sent cart abandonment campaign '{campaign.name}' to {customer.first_name}")
                    
                    return {
                        "status": "sent",
                        "campaign": campaign.name,
                        "customer": customer.first_name,
                        "offer_code": offer_code,
                        "message_id": whatsapp_result['message_id']
                    }
            
            return {"status": "failed", "reason": "No WhatsApp number or service unavailable"}
            
        except Exception as e:
            logger.error(f"❌ Failed to send campaign message: {e}")
            return {"status": "error", "error": str(e)}
    
    def run_cart_abandonment_campaigns(self, db: Session) -> Dict:
        """
        Main function to run all cart abandonment campaigns
        """
        logger.info("🚀 Running cart abandonment campaigns...")
        
        # Find carts ready for campaigns
        ready_carts = self.find_abandoned_carts_for_campaigns(db)
        
        if not ready_carts:
            return {
                "status": "completed",
                "messages_sent": 0,
                "message": "No abandoned carts ready for campaigns"
            }
        
        # Send campaign messages
        sent_count = 0
        failed_count = 0
        results = []
        
        for cart_data in ready_carts:
            result = self.send_campaign_message(db, cart_data)
            results.append(result)
            
            if result["status"] == "sent":
                sent_count += 1
            else:
                failed_count += 1
        
        logger.info(f"📊 Campaign results: {sent_count} sent, {failed_count} failed")
        
        return {
            "status": "completed",
            "messages_sent": sent_count,
            "messages_failed": failed_count,
            "total_processed": len(ready_carts),
            "results": results
        }
    
    def mark_cart_recovered(self, db: Session, cart_item_id: str, order_id: str) -> bool:
        """
        Mark cart as recovered when customer completes purchase
        """
        cart = db.query(CartItem).filter(CartItem.id == cart_item_id).first()
        if cart:
            cart.is_recovered = True
            cart.recovered_at = datetime.utcnow()
            cart.recovered_order_id = order_id
            
            # Mark campaign sends as converted
            campaign_sends = db.query(CampaignSend).filter(
                CampaignSend.cart_item_id == cart_item_id
            ).all()
            
            for send in campaign_sends:
                send.converted = True
                # Could calculate conversion amount here
            
            db.commit()
            logger.info(f"✅ Marked cart {cart_item_id} as recovered")
            return True
        
        return False