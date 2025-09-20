from typing import Optional, List, Dict
from datetime import datetime
from bson import ObjectId
from src.utils.db import fetch, insert, update
from src.utils.serialize_helper import serialize_doc
from src.services.chat_services import (
    get_conversation_by_id, 
    get_message_by_id, 
    increment_report_count,
    get_user_display_name
)
import uuid
import logging

logger = logging.getLogger(__name__)

# -------------------------
# REPORT CREATION
# -------------------------

async def create_report(
    reporter_id: str,
    target_type: str,  # "conversation" or "message"
    target_id: str,
    reason: str,
    custom_reason: Optional[str] = None,
    description: Optional[str] = None
) -> Optional[Dict]:
    """Create a new report for inappropriate content"""
    
    try:
        # Get target content and validate it exists
        if target_type == "conversation":
            target = await get_conversation_by_id(target_id)
            if not target:
                logger.error(f"Conversation {target_id} not found for report")
                return None
            location_id = target["location_id"]
            conversation_id = target_id
        else:  # message
            target = await get_message_by_id(target_id)
            if not target:
                logger.error(f"Message {target_id} not found for report")
                return None
            # Get conversation details for context
            conversation = await get_conversation_by_id(target["conversation_id"])
            if not conversation:
                logger.error(f"Conversation {target['conversation_id']} not found for message report")
                return None
            location_id = conversation["location_id"]
            conversation_id = target["conversation_id"]
        
        # Check for duplicate reports from same user
        existing_reports = await fetch("reports", {
            "reporter_id": reporter_id,
            "target_id": target_id,
            "status": {"$in": ["pending", "reviewed"]}
        })
        
        if existing_reports:
            logger.info(f"User {reporter_id} already reported {target_type} {target_id}")
            return None  # Already reported by this user
        
        # Get reporter information
        reporter_name = await get_user_display_name(reporter_id)
        
        # Calculate priority based on reason
        priority = calculate_priority(reason)
        
        # Create report document
        report_data = {
            "id": str(uuid.uuid4()),
            "reporter_id": reporter_id,
            "reporter_name": reporter_name,
            
            # Target content info
            "target_type": target_type,
            "target_id": target_id,
            "target_content": target.get("title", "") if target_type == "conversation" else target.get("content", ""),
            "target_author_id": target["author_id"],
            "target_author_name": target["author_name"],
            
            # Report details
            "reason": reason,
            "custom_reason": custom_reason.strip() if custom_reason else None,
            "description": description.strip() if description else None,
            
            # Context
            "location_id": location_id,
            "conversation_id": conversation_id,
            
            # Status tracking
            "status": "pending",
            "priority": priority,
            "admin_notes": None,
            "resolved_by": None,
            "resolved_at": None,
            
            # Timestamps
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            
            # Analytics
            "report_count": 1
        }
        
        # Insert report into database
        report_id = await insert("reports", report_data)
        if not report_id:
            logger.error(f"Failed to insert report for {target_type} {target_id}")
            return None
        
        # Update target content report count
        await increment_report_count(target_type, target_id)
        
        # Check if we need to notify admins about high-priority content
        await check_urgent_reports(target_type, target_id)
        
        logger.info(f"Report created: {report_data['id']} for {target_type} {target_id} by user {reporter_id}")
        
        return serialize_doc(report_data)
        
    except Exception as e:
        logger.error(f"Error creating report: {e}")
        return None

# -------------------------
# REPORT UTILITIES
# -------------------------

def calculate_priority(reason: str) -> str:
    """Calculate report priority based on reason"""
    high_priority_reasons = ["harassment", "inappropriate"]
    medium_priority_reasons = ["spam", "misinformation"] 
    
    if reason in high_priority_reasons:
        return "high"
    elif reason in medium_priority_reasons:
        return "medium"
    else:
        return "low"

async def check_urgent_reports(target_type: str, target_id: str):
    """Check if content needs urgent admin attention"""
    try:
        # Count pending reports for this content
        reports = await fetch("reports", {
            "target_id": target_id,
            "status": "pending"
        })
        
        report_count = len(reports) if reports else 0
        
        # Log urgent cases for admin attention
        if report_count >= 2:
            logger.warning(
                f"URGENT: {target_type.title()} {target_id} has {report_count} pending reports"
            )
        
        # You could add webhook/email notifications here for your admin dashboard
        
    except Exception as e:
        logger.error(f"Error checking urgent reports: {e}")

# -------------------------
# REPORT QUERIES (FOR ADMIN DASHBOARD)
# -------------------------

async def get_reports_by_status(
    status: Optional[str] = None,
    location_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) -> Optional[List[Dict]]:
    """Get reports filtered by status and location"""
    
    try:
        query = {}
        
        if status:
            query["status"] = status
        if location_id:
            query["location_id"] = location_id
        
        skip = (page - 1) * limit
        
        reports = await fetch(
            "reports",
            query,
            skip=skip,
            limit=limit,
            sort=[("priority", -1), ("created_at", -1)]  # High priority first, then newest
        )
        
        if not reports:
            return []
        
        return [serialize_doc(report) for report in reports]
        
    except Exception as e:
        logger.error(f"Error fetching reports: {e}")
        return None

async def get_report_by_id(report_id: str) -> Optional[Dict]:
    """Get a specific report by ID"""
    try:
        reports = await fetch("reports", {"id": report_id})
        if not reports:
            return None
        return serialize_doc(reports[0])
    except Exception as e:
        logger.error(f"Error fetching report {report_id}: {e}")
        return None

async def get_reports_for_content(target_type: str, target_id: str) -> Optional[List[Dict]]:
    """Get all reports for a specific piece of content"""
    try:
        reports = await fetch("reports", {
            "target_type": target_type,
            "target_id": target_id
        }, sort=[("created_at", -1)])
        
        if not reports:
            return []
        
        return [serialize_doc(report) for report in reports]
        
    except Exception as e:
        logger.error(f"Error fetching reports for {target_type} {target_id}: {e}")
        return None

# -------------------------
# REPORT ANALYTICS
# -------------------------

async def get_report_statistics() -> Dict:
    """Get overall report statistics for admin dashboard"""
    try:
        # Total reports
        all_reports = await fetch("reports", {})
        total_reports = len(all_reports) if all_reports else 0
        
        # Pending reports
        pending_reports = await fetch("reports", {"status": "pending"})
        pending_count = len(pending_reports) if pending_reports else 0
        
        # Reports by reason
        reason_counts = {}
        if all_reports:
            for report in all_reports:
                reason = report.get("reason", "unknown")
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        # Most reported content
        content_reports = {}
        if all_reports:
            for report in all_reports:
                target_key = f"{report['target_type']}:{report['target_id']}"
                content_reports[target_key] = content_reports.get(target_key, 0) + 1
        
        return {
            "total_reports": total_reports,
            "pending_reports": pending_count,
            "resolved_reports": total_reports - pending_count,
            "reports_by_reason": reason_counts,
            "most_reported_content": dict(sorted(content_reports.items(), key=lambda x: x[1], reverse=True)[:10])
        }
        
    except Exception as e:
        logger.error(f"Error getting report statistics: {e}")
        return {
            "total_reports": 0,
            "pending_reports": 0, 
            "resolved_reports": 0,
            "reports_by_reason": {},
            "most_reported_content": {}
        }