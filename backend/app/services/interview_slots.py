"""Synthetic demo availability; office rules are examples, not BJIT policy."""
from datetime import datetime,timedelta,timezone,time
from zoneinfo import ZoneInfo
ZONE=ZoneInfo('Asia/Dhaka')

def offered_slots(now=None):
 now=now or datetime.now(timezone.utc);today=now.astimezone(ZONE).date();slots=[]
 for offset in range(14):
  day=today+timedelta(days=offset)
  if day.weekday()>4:continue
  starts=[(8,0),(9,0),(10,0),(11,0)]+([(14,0),(15,0),(16,0)] if day.weekday()==4 else [(13,30),(14,30),(15,30)])
  for hour,minute in starts:
   value=datetime.combine(day,time(hour,minute),ZONE).astimezone(timezone.utc)
   if value>now:slots.append(value)
 return slots
