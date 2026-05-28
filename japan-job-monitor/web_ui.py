"""
Web 管理界面 - Flask 应用
提供可视化界面查看监测状态、历史记录和配置
"""

from flask import Flask, render_template, jsonify, request
import sqlite3
import os
import yaml
from datetime import datetime
import logging

app = Flask(__name__)

# 配置路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'monitor.db')
SOURCES_PATH = os.path.join(BASE_DIR, 'config', 'sources.yaml')
KEYWORDS_PATH = os.path.join(BASE_DIR, 'config', 'keywords.txt')

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    """主页 - 显示概览仪表板"""
    return render_template('index.html')


@app.route('/api/stats')
def get_stats():
    """获取统计信息"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 总记录数
        cursor.execute("SELECT COUNT(*) as total FROM seen_items")
        total = cursor.fetchone()['total']
        
        # 今日新增
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(
            "SELECT COUNT(*) as new_today FROM seen_items WHERE date(first_seen) = ?",
            (today,)
        )
        new_today = cursor.fetchone()['new_today']
        
        # 已通知数
        cursor.execute("SELECT COUNT(*) as notified FROM seen_items WHERE notified = 1")
        notified = cursor.fetchone()['notified']
        
        # 按类型统计
        cursor.execute("""
            SELECT item_type, COUNT(*) as count 
            FROM seen_items 
            GROUP BY item_type
        """)
        by_type = {row['item_type']: row['count'] for row in cursor.fetchall()}
        
        # 按来源统计
        cursor.execute("""
            SELECT source_name, COUNT(*) as count 
            FROM seen_items 
            GROUP BY source_name 
            ORDER BY count DESC
            LIMIT 10
        """)
        by_source = {row['source_name']: row['count'] for row in cursor.fetchall()}
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'total': total,
                'new_today': new_today,
                'notified': notified,
                'by_type': by_type,
                'by_source': by_source
            }
        })
    except Exception as e:
        logger.error(f"获取统计信息失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/history')
def get_history():
    """获取历史记录（支持分页和筛选）"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        item_type = request.args.get('type', '')
        source = request.args.get('source', '')
        
        offset = (page - 1) * per_page
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = []
        params = []
        
        if item_type:
            conditions.append("item_type = ?")
            params.append(item_type)
        
        if source:
            conditions.append("source_name = ?")
            params.append(source)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # 查询总数
        count_query = f"SELECT COUNT(*) as total FROM seen_items {where_clause}"
        cursor.execute(count_query, params)
        total = cursor.fetchone()['total']
        
        # 查询数据
        query = f"""
            SELECT id, source_name, item_type, unique_key, title, url, 
                   first_seen, notified
            FROM seen_items 
            {where_clause}
            ORDER BY first_seen DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        
        items = []
        for row in rows:
            items.append({
                'id': row['id'],
                'source_name': row['source_name'],
                'item_type': row['item_type'],
                'title': row['title'] or 'N/A',
                'url': row['url'] or 'N/A',
                'first_seen': row['first_seen'],
                'notified': bool(row['notified'])
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'items': items,
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': total,
                    'total_pages': (total + per_page - 1) // per_page
                }
            }
        })
    except Exception as e:
        logger.error(f"获取历史记录失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sources')
def get_sources():
    """获取数据源配置"""
    try:
        with open(SOURCES_PATH, 'r', encoding='utf-8') as f:
            sources = yaml.safe_load(f)
        
        return jsonify({
            'success': True,
            'data': sources
        })
    except Exception as e:
        logger.error(f"读取数据源配置失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/keywords')
def get_keywords():
    """获取关键词列表"""
    try:
        with open(KEYWORDS_PATH, 'r', encoding='utf-8') as f:
            keywords = [line.strip() for line in f if line.strip()]
        
        return jsonify({
            'success': True,
            'data': keywords
        })
    except Exception as e:
        logger.error(f"读取关键词失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs')
def get_logs():
    """获取最新日志（最后 100 行）"""
    try:
        log_path = os.path.join(BASE_DIR, 'monitor.log')
        if not os.path.exists(log_path):
            return jsonify({'success': True, 'data': []})
        
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            last_100 = lines[-100:] if len(lines) > 100 else lines
        
        return jsonify({
            'success': True,
            'data': ''.join(last_100)
        })
    except Exception as e:
        logger.error(f"读取日志失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/run', methods=['POST'])
def run_monitor():
    """触发手动运行监测任务"""
    try:
        import subprocess
        # 异步执行 main.py
        result = subprocess.run(
            ['python', os.path.join(BASE_DIR, 'main.py')],
            capture_output=True,
            text=True,
            timeout=300  # 5 分钟超时
        )
        
        return jsonify({
            'success': True,
            'data': {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': '执行超时（超过 5 分钟）'
        }), 408
    except Exception as e:
        logger.error(f"触发监测任务失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    # 创建必要的目录
    template_dir = os.path.join(BASE_DIR, 'templates')
    static_dir = os.path.join(BASE_DIR, 'static')
    os.makedirs(template_dir, exist_ok=True)
    os.makedirs(static_dir, exist_ok=True)
    
    # 启动 Flask 应用
    app.run(host='0.0.0.0', port=5000, debug=False)
