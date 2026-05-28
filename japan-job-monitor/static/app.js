/**
 * 赴日工作信息监测系统 - 前端 JavaScript
 */

// 全局状态
let currentPage = 1;
let currentFilters = { type: '', source: '', priority: '', tag: '' };

// DOM 加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initTabs();
    loadStats();
    loadHistory();
    loadSources();
    loadKeywords();
    loadAllTags(); // 加载所有标签用于筛选
    
    // 绑定事件
    document.getElementById('run-now-btn').addEventListener('click', runMonitor);
    document.getElementById('apply-filter').addEventListener('click', applyFilter);
    document.getElementById('clear-filter').addEventListener('click', clearFilter);
    document.getElementById('refresh-logs').addEventListener('click', loadLogs);
    
    // 自动刷新统计（每 30 秒）
    setInterval(loadStats, 30000);
});

/**
 * 标签页切换
 */
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            const tabId = this.dataset.tab;
            
            // 移除所有 active
            tabBtns.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // 添加 active
            this.classList.add('active');
            document.getElementById(tabId).classList.add('active');
            
            // 加载对应内容
            if (tabId === 'history') loadHistory();
            if (tabId === 'sources') loadSources();
            if (tabId === 'logs') loadLogs();
            if (tabId === 'settings') loadKeywords();
        });
    });
}

/**
 * 加载统计数据
 */
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const result = await response.json();
        
        if (result.success) {
            const data = result.data;
            document.getElementById('total-count').textContent = data.total;
            document.getElementById('new-today').textContent = data.new_today;
            document.getElementById('notified-count').textContent = data.notified;
            
            // 渲染图表
            renderChart('by-type-chart', data.by_type);
            renderChart('by-source-chart', data.by_source);
            
            // 加载最近活动
            loadRecentActivity();
        }
    } catch (error) {
        console.error('加载统计数据失败:', error);
    }
}

/**
 * 渲染柱状图
 */
function renderChart(containerId, data) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const entries = Object.entries(data);
    if (entries.length === 0) {
        container.innerHTML = '<p class="loading">暂无数据</p>';
        return;
    }
    
    const maxValue = Math.max(...entries.map(([_, v]) => v));
    
    let html = '';
    entries.forEach(([label, value]) => {
        const percentage = maxValue > 0 ? (value / maxValue * 100) : 0;
        html += `
            <div class="chart-bar">
                <div class="chart-bar-label">${label}</div>
                <div class="chart-bar-fill">
                    <div class="chart-bar-value" style="width: ${percentage}%">${value}</div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

/**
 * 加载最近活动
 */
async function loadRecentActivity() {
    try {
        const response = await fetch('/api/history?page=1&per_page=5');
        const result = await response.json();
        
        if (result.success) {
            const tbody = document.querySelector('#recent-table tbody');
            if (result.data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="loading">暂无记录</td></tr>';
                return;
            }
            
            let html = '';
            result.data.items.forEach(item => {
                html += `
                    <tr>
                        <td>${escapeHtml(item.source_name)}</td>
                        <td><span class="source-type">${item.item_type}</span></td>
                        <td>${escapeHtml(item.title)}</td>
                        <td>${formatDate(item.first_seen)}</td>
                        <td>
                            <span class="status-badge ${item.notified ? 'status-notified' : 'status-pending'}">
                                ${item.notified ? '已通知' : '待通知'}
                            </span>
                        </td>
                    </tr>
                `;
            });
            
            tbody.innerHTML = html;
        }
    } catch (error) {
        console.error('加载最近活动失败:', error);
    }
}

/**
 * 加载历史记录
 */
async function loadHistory(page = 1) {
    currentPage = page;
    
    try {
        let url = `/api/history?page=${page}&per_page=20`;
        if (currentFilters.type) url += `&type=${encodeURIComponent(currentFilters.type)}`;
        if (currentFilters.source) url += `&source=${encodeURIComponent(currentFilters.source)}`;
        if (currentFilters.priority) url += `&priority=${encodeURIComponent(currentFilters.priority)}`;
        if (currentFilters.tag) url += `&tag=${encodeURIComponent(currentFilters.tag)}`;
        
        const response = await fetch(url);
        const result = await response.json();
        
        if (result.success) {
            const tbody = document.querySelector('#history-table tbody');
            const data = result.data;
            
            if (data.items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" class="loading">暂无记录</td></tr>';
            } else {
                let html = '';
                data.items.forEach(item => {
                    // 优先级徽章
                    const priorityClass = `priority-${item.priority}`;
                    const priorityLabel = item.priority === 'critical' ? '🔴 紧急' : 
                                         (item.priority === 'high' ? '🟠 重要' : '⚪ 常规');
                    
                    // 通知渠道图标
                    let channelsHtml = '';
                    if (item.notify_channels && item.notify_channels.length > 0) {
                        channelsHtml = item.notify_channels.map(ch => {
                            const icon = ch === 'email' ? '📧' : '💬';
                            return `<span class="channel-icon">${icon}</span>`;
                        }).join(' ');
                    } else {
                        channelsHtml = '-';
                    }
                    
                    // 标签显示
                    let tagsHtml = '';
                    if (item.tags && item.tags.length > 0) {
                        tagsHtml = item.tags.map(tag => `<span class="tag-badge">${escapeHtml(tag)}</span>`).join('');
                    } else {
                        tagsHtml = '-';
                    }
                    
                    html += `
                        <tr>
                            <td>${item.id}</td>
                            <td><span class="priority-badge ${priorityClass}">${priorityLabel}</span></td>
                            <td>${escapeHtml(item.source_name)}</td>
                            <td><span class="source-type">${item.item_type}</span></td>
                            <td>${escapeHtml(item.title)}</td>
                            <td>${item.url !== 'N/A' ? `<a href="${escapeHtml(item.url)}" target="_blank">链接</a>` : '-'}</td>
                            <td>${formatDate(item.first_seen)}</td>
                            <td>${channelsHtml}</td>
                            <td>${tagsHtml}</td>
                        </tr>
                    `;
                });
                tbody.innerHTML = html;
            }
            
            // 渲染分页
            renderPagination(data.pagination);
        }
    } catch (error) {
        console.error('加载历史记录失败:', error);
    }
}

/**
 * 渲染分页
 */
function renderPagination(pagination) {
    const container = document.getElementById('pagination');
    const { page, total_pages } = pagination;
    
    if (total_pages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // 上一页
    if (page > 1) {
        html += `<button class="page-btn" onclick="loadHistory(${page - 1})">上一页</button>`;
    }
    
    // 页码
    for (let i = Math.max(1, page - 2); i <= Math.min(total_pages, page + 2); i++) {
        html += `<button class="page-btn ${i === page ? 'active' : ''}" onclick="loadHistory(${i})">${i}</button>`;
    }
    
    // 下一页
    if (page < total_pages) {
        html += `<button class="page-btn" onclick="loadHistory(${page + 1})">下一页</button>`;
    }
    
    container.innerHTML = html;
}

/**
 * 应用筛选
 */
function applyFilter() {
    const typeSelect = document.getElementById('filter-type');
    const sourceSelect = document.getElementById('filter-source');
    const prioritySelect = document.getElementById('filter-priority');
    const tagSelect = document.getElementById('filter-tag');
    
    currentFilters = {
        type: typeSelect.value,
        source: sourceSelect.value,
        priority: prioritySelect.value,
        tag: tagSelect.value
    };
    
    loadHistory(1);
}

/**
 * 清除筛选
 */
function clearFilter() {
    document.getElementById('filter-type').value = '';
    document.getElementById('filter-source').value = '';
    document.getElementById('filter-priority').value = '';
    document.getElementById('filter-tag').value = '';
    currentFilters = { type: '', source: '', priority: '', tag: '' };
    loadHistory(1);
}

/**
 * 加载数据源
 */
async function loadSources() {
    try {
        const response = await fetch('/api/sources');
        const result = await response.json();
        
        if (result.success) {
            const container = document.getElementById('sources-list');
            // result.data 是包含 sources 数组的对象
            const sources = result.data.sources || [];
            
            if (sources.length === 0) {
                container.innerHTML = '<p class="loading">暂无数据源配置</p>';
                return;
            }
            
            let html = '';
            sources.forEach(source => {
                html += `
                    <div class="source-item">
                        <div class="source-info">
                            <h4>${escapeHtml(source.name)}</h4>
                            <div class="source-meta">
                                <span>类型：<span class="source-type">${source.type}</span></span>
                                <span>推送：${source.channel || '未设置'}</span>
                            </div>
                            <div class="source-meta" style="margin-top: 5px;">
                                <span style="font-size: 0.85em; color: #6c757d;">${escapeHtml(source.url)}</span>
                            </div>
                            ${source.note ? `<div class="source-meta" style="margin-top: 3px; font-size: 0.8em; color: #6c757d;">${escapeHtml(source.note)}</div>` : ''}
                        </div>
                    </div>
                `;
            });
            
            container.innerHTML = html;
            
            // 更新筛选器的来源选项
            updateSourceFilter(sources);
        }
    } catch (error) {
        console.error('加载数据源失败:', error);
    }
}

/**
 * 更新来源筛选器选项
 */
function updateSourceFilter(sources) {
    const select = document.getElementById('filter-source');
    if (!select) return; // 如果筛选器不存在则跳过
    
    const currentValue = select.value;
    
    let html = '<option value="">全部来源</option>';
    sources.forEach(source => {
        html += `<option value="${escapeHtml(source.name)}">${escapeHtml(source.name)}</option>`;
    });
    
    select.innerHTML = html;
    if (currentValue) select.value = currentValue;
}

/**
 * 加载日志
 */
async function loadLogs() {
    try {
        const response = await fetch('/api/logs');
        const result = await response.json();
        
        if (result.success) {
            const content = document.getElementById('logs-content');
            content.textContent = result.data || '暂无日志';
            content.scrollTop = content.scrollHeight;
        }
    } catch (error) {
        console.error('加载日志失败:', error);
    }
}

/**
 * 加载关键词
 */
async function loadKeywords() {
    try {
        const response = await fetch('/api/keywords');
        const result = await response.json();
        
        if (result.success) {
            const container = document.getElementById('keywords-list');
            const keywords = result.data || [];
            
            if (keywords.length === 0) {
                container.innerHTML = '<p class="loading">暂无关键词</p>';
                return;
            }
            
            let html = '';
            keywords.forEach(kw => {
                html += `<span class="keyword-tag">${escapeHtml(kw)}</span>`;
            });
            
            container.innerHTML = html;
        }
    } catch (error) {
        console.error('加载关键词失败:', error);
    }
}

/**
 * 运行监测任务
 */
async function runMonitor() {
    const btn = document.getElementById('run-now-btn');
    btn.disabled = true;
    btn.textContent = '运行中...';
    
    try {
        const response = await fetch('/api/run', { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            alert('监测任务执行完成！\n\n返回码：' + result.data.returncode);
            loadStats(); // 刷新统计
        } else {
            alert('执行失败：' + result.error);
        }
    } catch (error) {
        alert('执行出错：' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '立即运行';
    }
}

/**
 * 工具函数：转义 HTML
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 工具函数：格式化日期
 */
function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * 加载所有标签（用于筛选器）
 */
async function loadAllTags() {
    try {
        // 先获取一批历史记录来提取所有标签
        const response = await fetch('/api/history?per_page=100');
        const result = await response.json();
        
        if (result.success) {
            const allTags = new Set();
            result.data.items.forEach(item => {
                if (item.tags && Array.isArray(item.tags)) {
                    item.tags.forEach(tag => allTags.add(tag));
                }
            });
            
            // 填充标签筛选器
            const tagSelect = document.getElementById('filter-tag');
            if (tagSelect) {
                let html = '<option value="">全部标签</option>';
                Array.from(allTags).sort().forEach(tag => {
                    html += `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`;
                });
                tagSelect.innerHTML = html;
            }
            
            // 同时更新来源筛选器（如果还没加载）
            updateSourceFilterFromAPI();
        }
    } catch (error) {
        console.error('加载标签失败:', error);
    }
}

/**
 * 从 API 加载来源筛选器选项
 */
async function updateSourceFilterFromAPI() {
    try {
        const response = await fetch('/api/sources');
        const result = await response.json();
        
        if (result.success) {
            const sources = result.data.sources || [];
            updateSourceFilter(sources);
        }
    } catch (error) {
        console.error('加载来源筛选器失败:', error);
    }
}

