#!/usr/bin/env python3
"""
Simple test to check Query object handling
"""
from fastapi import Query
from typing import Optional

def test_query_objects():
    """Test what Query objects look like"""
    
    # This is what FastAPI creates
    limit_param = Query(50, le=100)
    source_param = Query(None)
    topic_param = Query(None)
    
    print(f"limit_param: {limit_param}")
    print(f"source_param: {source_param}")
    print(f"topic_param: {topic_param}")
    print(f"type of source_param: {type(source_param)}")
    print(f"value of source_param: {source_param}")
    
    # This is what we need in SQLAlchemy
    if source_param:
        print("source_param is truthy")
    else:
        print("source_param is falsy")

if __name__ == "__main__":
    test_query_objects()
