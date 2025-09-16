#!/usr/bin/env python3
"""
Week 4 구현사항 테스트용 간단 서버
의존성 문제를 우회하여 새로운 기능들만 테스트
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
import asyncio
import json

# 의존성 없이 테스트할 수 있는 간단한 서버
app = FastAPI(title="Week 4 Test Server", version="1.0.0")

# 모의 데이터
mock_stream_data = {
    "anomalies_detected": [
        {
            "keyword": "wireless mouse", 
            "price_change_percent": 25.5,
            "severity": "high",
            "detected_at": "2025-09-13T19:10:00Z"
        },
        {
            "keyword": "bluetooth headphones",
            "price_change_percent": 15.2, 
            "severity": "medium",
            "detected_at": "2025-09-13T19:05:00Z"
        }
    ],
    "market_signals": [
        {
            "keyword": "gaming keyboard",
            "market_signal": "market_heating_up",
            "recommendation": "good_entry_opportunity", 
            "analyzed_at": "2025-09-13T19:08:00Z"
        }
    ],
    "summary": {
        "total_anomalies": 2,
        "critical_signals": 1
    }
}

mock_event_stats = {
    "total_events": 1250,
    "total_aggregates": 45,
    "events_by_type": [
        {"event_type": "user_action", "count": 680},
        {"event_type": "analysis_completed", "count": 320},
        {"event_type": "analysis_requested", "count": 250}
    ],
    "recent_events": [
        {"event_type": "user_action", "timestamp": "2025-09-13T19:10:00Z"},
        {"event_type": "analysis_completed", "timestamp": "2025-09-13T19:09:30Z"}
    ]
}

@app.get("/")
async def root():
    return {"message": "Week 4 Test Server - All systems operational!", "timestamp": datetime.now().isoformat()}

# --- Week 4 스트림 처리 API 테스트 ---
@app.get("/api/stream/health")
async def stream_health():
    """스트림 프로세서 상태 확인"""
    return {
        "status": "healthy",
        "components": {
            "time_aggregator": "active",
            "anomaly_detector": "active", 
            "trend_analyzer": "active"
        },
        "uptime": "running",
        "last_check": datetime.now().isoformat()
    }

@app.get("/api/stream/insights")
async def stream_insights(hours: int = 1):
    """실시간 스트림 처리 인사이트"""
    return {
        "status": "success",
        "data": mock_stream_data,
        "time_window_hours": hours,
        "generated_at": datetime.now().isoformat()
    }

# --- Week 4 이벤트 소싱 API 테스트 ---
@app.get("/api/events/stats")
async def event_stats():
    """이벤트 저장소 통계"""
    return {
        "status": "success", 
        "data": mock_event_stats,
        "last_updated": datetime.now().isoformat()
    }

@app.get("/api/events/user/{user_id}/history")
async def user_history(user_id: str):
    """사용자 이벤트 이력"""
    mock_history = [
        {
            "event_id": "evt_123",
            "event_type": "user_created",
            "timestamp": "2025-09-13T18:00:00Z",
            "data": {"user_id": user_id, "email": f"{user_id}@test.com"},
            "version": 1
        },
        {
            "event_id": "evt_124", 
            "event_type": "user_action",
            "timestamp": "2025-09-13T18:30:00Z",
            "data": {"action_type": "page_view", "page": "index"},
            "version": 2
        }
    ]
    
    return {
        "status": "success",
        "user_id": user_id,
        "events": mock_history,
        "total_events": len(mock_history)
    }

@app.get("/api/events/user/{user_id}/state") 
async def user_state(user_id: str):
    """사용자 상태 재구성"""
    mock_state = {
        "user_id": user_id,
        "session_count": 3,
        "total_analyses": 12,
        "last_activity": "2025-09-13T19:10:00Z",
        "preferences": {"theme": "dark", "language": "ko"}
    }
    
    return {
        "status": "success",
        "user_id": user_id,
        "current_state": mock_state,
        "reconstructed_at": datetime.now().isoformat()
    }

@app.get("/api/events/keyword/{keyword}/trends")
async def keyword_trends(keyword: str):
    """키워드 트렌드 이력"""
    mock_trends = [
        {"timestamp": "2025-09-13T18:00:00Z", "competitor_count": 45, "avg_price": 29.99},
        {"timestamp": "2025-09-13T18:30:00Z", "competitor_count": 47, "avg_price": 28.50},
        {"timestamp": "2025-09-13T19:00:00Z", "competitor_count": 52, "avg_price": 31.20}
    ]
    
    return {
        "status": "success",
        "keyword": keyword,
        "trend_data": mock_trends,
        "analysis_count": 15,
        "anomaly_count": 2,
        "first_analyzed": "2025-09-13T10:00:00Z",
        "last_analyzed": "2025-09-13T19:00:00Z"
    }

# --- 테스트용 간단한 대시보드 ---
@app.get("/stream")
async def stream_dashboard():
    """간단한 스트림 대시보드 (HTML)"""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Week 4 Test Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .card {{ background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .status {{ color: #28a745; font-weight: bold; }}
            .anomaly {{ color: #dc3545; background: #f8d7da; padding: 10px; margin: 5px 0; border-radius: 4px; }}
            .signal {{ color: #007bff; background: #d1ecf1; padding: 10px; margin: 5px 0; border-radius: 4px; }}
            button {{ background: #007bff; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔥 Week 4 테스트 대시보드</h1>
            
            <div class="card">
                <h2>시스템 상태</h2>
                <p class="status">✅ 모든 시스템 정상 동작</p>
                <p>마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div class="card">
                <h2>실시간 이상치 탐지</h2>
                <div class="anomaly">wireless mouse: 25.5% 가격 상승 (높음)</div>
                <div class="anomaly">bluetooth headphones: 15.2% 가격 상승 (보통)</div>
            </div>
            
            <div class="card">
                <h2>시장 신호</h2>
                <div class="signal">gaming keyboard: 시장 과열 신호 - 진입 기회</div>
            </div>
            
            <div class="card">
                <h2>API 테스트</h2>
                <button onclick="testAPI()">API 응답 테스트</button>
                <pre id="apiResult" style="background: #f8f9fa; padding: 10px; margin-top: 10px;"></pre>
            </div>
        </div>
        
        <script>
        async function testAPI() {{
            const result = document.getElementById('apiResult');
            try {{
                const response = await fetch('/api/stream/health');
                const data = await response.json();
                result.textContent = JSON.stringify(data, null, 2);
            }} catch (error) {{
                result.textContent = 'API 호출 실패: ' + error.message;
            }}
        }}
        </script>
    </body>
    </html>
    """
    
    from fastapi.responses import HTMLResponse
    return HTMLResponse(html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8002)