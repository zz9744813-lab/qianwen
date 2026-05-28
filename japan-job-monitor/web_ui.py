"""
Web 管理界面 - Flask 应用
提供可视化界面查看监测状态、历史记录和配置
支持优先级分类、提醒过滤等功能
"""

from flask import Flask, render_template, jsonify, request, send_file
import sqlite3
import os
import yaml
from datetime import datetime, timedelta
import logging
import io

app = Flask(__name__)

# 配置路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'monitor.db')
SOURCES_PATH = os.path.join(BASE_DIR, 'config', 'sources.yaml')
KEYWORDS_PATH = os.path.join(BASE_DIR, 'config', 'keywords.txt')
LOG_PATH = os.path.join(BASE_DIR, 'monitor.log')

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_sources_config():
    """加载数据源配置"""
    try:
        with open(SOURCES_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"读取数据源配置失败：{e}")
        return {'sources': []}


@app.route('/')
def index():
    """主页 - 显示概览仪表板"""
    return render_template('index.html')


@app.route('/api/stats')
def get_stats():
    """获取统计信息（包含优先级分布）"""
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
        
        # 紧急提醒数（critical 优先级）
        cursor.execute("SELECT COUNT(*) as critical FROM seen_items WHERE priority = 'critical'")
        critical = cursor.fetchone()['critical']
        
        # 按类型统计
        cursor.execute("""
            SELECT item_type, COUNT(*) as count 
            FROM seen_items 
            GROUP BY item_type
        """)
        by_type = {row['item_type']: row['count'] for row in cursor.fetchall()}
        
        # 按优先级统计
        cursor.execute("""
            SELECT priority, COUNT(*) as count 
            FROM seen_items 
            GROUP BY priority
        """)
        by_priority = {'critical': 0, 'high': 0, 'normal': 0}
        for row in cursor.fetchall():
            priority = row['priority'] or 'normal'
            if priority in by_priority:
                by_priority[priority] = row['count']
        
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
                'critical': critical,
                'by_type': by_type,
                'by_priority': by_priority,
                'by_source': by_source
            }
        })
    except Exception as e:
        logger.error(f"获取统计信息失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/history')
def get_history():
    """获取历史记录（支持分页和筛选，包含优先级）"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        item_type = request.args.get('type', '')
        source = request.args.get('source', '')
        priority = request.args.get('priority', '')
        
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
        
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        
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
                   first_seen, notified, priority, notify_channels
            FROM seen_items 
            {where_clause}
            ORDER BY first_seen DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [per_page, offset])
        rows = cursor.fetchall()
        
        items = []
        for row in rows:
            # 解析 notify_channels
            notify_channels = []
            if row['notify_channels']:
                try:
                    notify_channels = row['notify_channels'].split(',')
                except:
                    pass
            
            items.append({
                'id': row['id'],
                'source_name': row['source_name'],
                'item_type': row['item_type'],
                'title': row['title'] or 'N/A',
                'url': row['url'] or 'N/A',
                'first_seen': row['first_seen'],
                'notified': bool(row['notified']),
                'priority': row['priority'] or 'normal',
                'notify_channels': notify_channels
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


@app.route('/api/alerts')
def get_alerts():
    """获取提醒列表（按优先级排序，支持过滤）"""
    try:
        limit = int(request.args.get('limit', 50))
        filter_type = request.args.get('filter', 'all')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 构建查询条件
        conditions = ["notified = 1"]  # 只显示已通知的
        params = []
        
        if filter_type == 'critical':
            conditions.append("priority = 'critical'")
        elif filter_type == 'high':
            conditions.append("priority = 'high'")
        elif filter_type == 'email':
            conditions.append("notify_channels LIKE '%email%'")
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        query = f"""
            SELECT id, source_name, item_type, title, url, 
                   first_seen, notified, priority, notify_channels
            FROM seen_items 
            {where_clause}
            ORDER BY 
                CASE priority 
                    WHEN 'critical' THEN 1 
                    WHEN 'high' THEN 2 
                    ELSE 3 
                END,
                first_seen DESC
            LIMIT ?
        """
        cursor.execute(query, params + [limit])
        rows = cursor.fetchall()
        
        alerts = []
        for row in rows:
            notify_channels = []
            if row['notify_channels']:
                try:
                    notify_channels = row['notify_channels'].split(',')
                except:
                    pass
            
            alerts.append({
                'id': row['id'],
                'source_name': row['source_name'],
                'item_type': row['item_type'],
                'title': row['title'] or 'N/A',
                'url': row['url'] or 'N/A',
                'first_seen': row['first_seen'],
                'priority': row['priority'] or 'normal',
                'notify_channels': notify_channels
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'data': {
                'alerts': alerts
            }
        })
    except Exception as e:
        logger.error(f"获取提醒列表失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sources')
def get_sources():
    """获取数据源配置"""
    try:
        config = load_sources_config()
        sources = config.get('sources', [])
        
        return jsonify({
            'success': True,
            'data': {
                'sources': sources,
                'enable_translation': config.get('enable_translation', False),
                'fetch_settings': config.get('fetch_settings', {})
            }
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
    """获取最新日志（支持级别过滤）"""
    try:
        level_filter = request.args.get('level', 'all')
        
        if not os.path.exists(LOG_PATH):
            return jsonify({'success': True, 'data': ''})
        
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # 根据级别过滤
            if level_filter != 'all':
                filtered_lines = [line for line in lines if level_filter in line]
                last_100 = filtered_lines[-100:] if len(filtered_lines) > 100 else filtered_lines
            else:
                last_100 = lines[-100:] if len(lines) > 100 else lines
        
        return jsonify({
            'success': True,
            'data': ''.join(last_100)
        })
    except Exception as e:
        logger.error(f"读取日志失败：{e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs/download')
def download_logs():
    """下载日志文件"""
    try:
        if not os.path.exists(LOG_PATH):
            return jsonify({'success': False, 'error': '日志文件不存在'}), 404
        
        return send_file(
            LOG_PATH,
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'monitor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
    except Exception as e:
        logger.error(f"下载日志失败：{e}")
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
                'stdout': result.stdout[:1000] if result.stdout else '',  # 限制长度
                'stderr': result.stderr[:1000] if result.stderr else ''
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
