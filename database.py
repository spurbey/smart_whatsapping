"""
Database models and connection setup
This file defines how your data is structured in the database
"""

from sqlalchemy import create_engine, Column, String, Float, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

# Database connection string - replace with your actual database URL
DATABASE_URL = "postgresql://postgres:water000@localhost:5432/ecommerce_automation"

# Create database engine - this handles connections to PostgreSQL
engine = create_engine(DATABASE_URL)

# Create session factory - sessions handle individual database transactions  
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all database models
Base = declarative_base()

# Database Models - these define your table structures

class Customer(Base):
    """
    Customer table - stores customer information
    This is like defining the structure of a spreadsheet
    """
    __tablename__ = "customers"  # Actual table name in database
    
    # Primary key - unique identifier for each customer
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Customer contact information
    email = Column(String, unique=True, nullable=True)  # nullable=True means can be empty
    phone = Column(String, unique=True, nullable=True)
    whatsapp_phone = Column(String, nullable=True)
    telegram_id = Column(String, nullable=True)
    
    # Customer details
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    
    # Business metrics
    total_orders = Column(Float, default=0.0)  # Total amount spent
    order_count = Column(Float, default=0)     # Number of orders
    
    # Timestamps - track when records are created/updated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - these create connections to other tables
    orders = relationship("Order", back_populates="customer")  # One customer can have many orders
    messages = relationship("Message", back_populates="customer")  # One customer can have many messages

class Order(Base):
    """
    Order table - stores order information from Shopify, WooCommerce, etc.
    """
    __tablename__ = "orders"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key - connects to customer table
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    
    # Order details
    platform_order_id = Column(String, nullable=False)  # Original order ID from Shopify/etc
    platform = Column(String, nullable=False)  # 'shopify', 'woocommerce', etc.
    
    # Financial information
    total_price = Column(Float, nullable=False)
    currency = Column(String, default="USD")
    
    # Order status
    status = Column(String, nullable=False)  # 'pending', 'shipped', 'delivered', etc.
    fulfillment_status = Column(String, nullable=True)
    
    # Order content (stored as JSON text for simplicity)
    items_json = Column(Text, nullable=True)  # JSON string of order items
    
    # Timestamps
    order_date = Column(DateTime, nullable=False)  # When order was placed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship back to customer
    customer = relationship("Customer", back_populates="orders")

class Message(Base):
    """
    Message table - stores all customer communications
    """
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Foreign key to customer
    customer_id = Column(String, ForeignKey("customers.id"), nullable=False)
    
    # Message details
    channel = Column(String, nullable=False)  # 'whatsapp', 'telegram', 'email', etc.
    direction = Column(String, nullable=False)  # 'inbound' or 'outbound'
    content = Column(Text, nullable=False)  # The actual message text
    
    # Platform-specific IDs
    platform_message_id = Column(String, nullable=True)  # WhatsApp message ID, etc.
    
    # Message metadata (stored as JSON)
    metadata_json = Column(Text, nullable=True)  # Additional data like attachments, etc.
    
    # Workflow tracking
    workflow_id = Column(String, nullable=True)  # Which automation workflow sent this
    bot_handled = Column(Boolean, default=False)  # Was this handled by bot or human?
    
    # Timestamps
    sent_at = Column(DateTime, nullable=True)  # When message was sent (for outbound)
    received_at = Column(DateTime, nullable=True)  # When message was received (for inbound)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship back to customer
    customer = relationship("Customer", back_populates="messages")

class WebhookEvent(Base):
    """
    Webhook events table - logs all incoming webhooks for debugging
    """
    __tablename__ = "webhook_events"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Webhook details
    source = Column(String, nullable=False)  # 'shopify', 'whatsapp', etc.
    event_type = Column(String, nullable=False)  # 'order.created', 'message.received', etc.
    
    # Raw webhook data
    raw_data = Column(Text, nullable=False)  # Complete JSON payload
    
    # Processing status
    processed = Column(Boolean, default=False)
    processing_error = Column(Text, nullable=True)
    
    # Timestamps
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

# Database helper functions

def get_database_session():
    """
    Create a database session for handling transactions
    Use this in your API endpoints to interact with the database
    """
    db = SessionLocal()
    try:
        return db
    finally:
        pass  # Session will be closed by the caller

def create_tables():
    """
    Create all tables in the database
    Run this once to set up your database schema
    """
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")

def drop_tables():
    """
    Delete all tables - useful for development/testing
    BE CAREFUL: This deletes all your data!
    """
    Base.metadata.drop_all(bind=engine)
    print("⚠️  All database tables dropped!")

# Database utility functions

def normalize_phone_number(phone):
    """
    Normalize phone number to consistent format
    """
    if not phone:
        return None
    
    # Remove common prefixes and normalize
    phone = phone.replace('whatsapp:', '').replace('+', '').replace(' ', '').replace('-', '')
    
    # Add country code if missing (assuming US +1 for demo)
    if len(phone) == 10:
        phone = '1' + phone
    
    return '+' + phone

def find_or_create_customer(db, email=None, phone=None, whatsapp_phone=None):
    """
    Find an existing customer or create a new one with improved duplicate prevention
    """
    # Normalize phone numbers
    normalized_phone = normalize_phone_number(phone)
    normalized_whatsapp = normalize_phone_number(whatsapp_phone)
    
    customer = None
    
    # Try to find by email first (most reliable)
    if email:
        customer = db.query(Customer).filter(Customer.email == email).first()
        if customer:
            # Update missing phone numbers if found by email
            if normalized_whatsapp and not customer.whatsapp_phone:
                customer.whatsapp_phone = normalized_whatsapp
                customer.updated_at = datetime.utcnow()
            if normalized_phone and not customer.phone:
                customer.phone = normalized_phone
                customer.updated_at = datetime.utcnow()
    
    # Try to find by any phone number (normalized)
    if not customer and (normalized_phone or normalized_whatsapp):
        search_phones = [p for p in [normalized_phone, normalized_whatsapp] if p]
        
        for search_phone in search_phones:
            customer = db.query(Customer).filter(
                (Customer.phone == search_phone) |
                (Customer.whatsapp_phone == search_phone)
            ).first()
            if customer:
                # Update missing information
                if email and not customer.email:
                    customer.email = email
                    customer.updated_at = datetime.utcnow()
                if normalized_whatsapp and not customer.whatsapp_phone:
                    customer.whatsapp_phone = normalized_whatsapp
                    customer.updated_at = datetime.utcnow()
                if normalized_phone and not customer.phone:
                    customer.phone = normalized_phone
                    customer.updated_at = datetime.utcnow()
                break
    
    # Create new customer if none found
    if not customer:
        customer = Customer(
            email=email,
            phone=normalized_phone,
            whatsapp_phone=normalized_whatsapp
        )
        db.add(customer)
        # Don't commit here - let the caller handle transactions
        db.flush()  # Get the ID without committing
        print(f"✅ Created new customer: {customer.id}")
    
    return customer

def recalculate_customer_totals(db, customer_id):
    """
    Recalculate customer totals from actual orders
    """
    from sqlalchemy import func
    
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        return None
    
    # Calculate totals from actual orders
    totals = db.query(
        func.count(Order.id).label('order_count'),
        func.coalesce(func.sum(Order.total_price), 0).label('total_spent')
    ).filter(Order.customer_id == customer_id).first()
    
    # Update customer record
    customer.order_count = totals.order_count
    customer.total_orders = float(totals.total_spent)
    customer.updated_at = datetime.utcnow()
    
    return customer
