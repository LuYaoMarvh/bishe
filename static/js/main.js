/**
 * NL2SQL 智能查询系统 - 前端交互逻辑
 */

// 全局状态
let currentQuestion = '';
let clarificationContext = null;
let historyPanelVisible = true;

// ==================================
// 页面加载完成后初始化
// ==================================
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 NL2SQL 系统加载完成');
    loadStats();
    loadHistory();

    // 自动调整输入框高度
    const queryInput = document.getElementById('queryInput');
    queryInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 200) + 'px';
    });
});

// ==================================
// 发送查询
// ==================================
async function sendQuery() {
    const input = document.getElementById('queryInput');
    const question = input.value.trim();

    if (!question) {
        alert('请输入问题');
        return;
    }

    // 安全检查：输入长度限制
    if (question.length > 2000) {
        alert('输入过长，请控制在2000个字符以内');
        return;
    }

    currentQuestion = question;

    // 禁用输入
    setLoading(true);

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question })
        });

        const data = await response.json();

        if (!data.success) {
            showError(data.error || '查询失败');
            return;
        }

        // 检查是否需要澄清
        if (data.needs_clarification) {
            showClarification(data);
            return;
        }

        // 显示结果
        displayResults(data);

        // 清空输入框
        input.value = '';
        input.style.height = 'auto';

        // 刷新历史和统计
        loadHistory();
        loadStats();

    } catch (error) {
        console.error('查询错误:', error);
        showError('网络错误，请检查连接');
    } finally {
        setLoading(false);
    }
}

// ==================================
// 显示结果
// ==================================
function displayResults(data) {
    const isChat = data.is_chat;

    if (isChat) {
        // 聊天响应：只显示答案，隐藏SQL和表格
        document.getElementById('sqlSection').style.display = 'none';
        document.getElementById('resultSection').style.display = 'none';

        const answerSection = document.getElementById('answerSection');
        const answerContent = document.getElementById('answerContent');

        answerSection.style.display = 'block';
        answerContent.innerHTML = formatAnswer(data.answer);

    } else {
        // SQL查询响应：显示完整结果
        document.getElementById('sqlSection').style.display = 'flex';
        document.getElementById('resultSection').style.display = 'flex';

        // 显示SQL
        displaySQL(data.sql);

        // 显示查询结果
        displayQueryResult(data.result);

        // 显示自然语言答案
        if (data.answer) {
            const answerSection = document.getElementById('answerSection');
            const answerContent = document.getElementById('answerContent');

            answerSection.style.display = 'block';
            answerContent.innerHTML = formatAnswer(data.answer);
        }
    }
}

// ==================================
// 显示SQL
// ==================================
function displaySQL(sql) {
    const sqlCode = document.getElementById('sqlCode');
    sqlCode.textContent = sql || '-- 未生成SQL';
}

// ==================================
// 显示查询结果
// ==================================
function displayQueryResult(result) {
    const resultContent = document.getElementById('resultContent');

    if (!result || result.row_count === 0) {
        resultContent.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <div class="empty-text">查询结果为空</div>
            </div>
        `;
        return;
    }

    const { columns, rows, row_count } = result;

    // 构建摘要
    let html = `
        <div class="result-summary">
            ✓ 查询成功，共找到 <strong>${row_count}</strong> 条记录
        </div>
    `;

    // 构建表格
    if (rows && rows.length > 0) {
        html += '<table class="result-table"><thead><tr>';

        // 表头
        columns.forEach(col => {
            html += `<th>${escapeHtml(col)}</th>`;
        });
        html += '</tr></thead><tbody>';

        // 数据行（最多显示100行）
        const displayRows = rows.slice(0, 100);
        displayRows.forEach(row => {
            html += '<tr>';
            Object.values(row).forEach(val => {
                html += `<td>${escapeHtml(String(val))}</td>`;
            });
            html += '</tr>';
        });

        html += '</tbody></table>';

        if (row_count > 100) {
            html += `<div class="result-summary" style="margin-top: 12px;">
                ⚠️ 数据过多，仅显示前100行
            </div>`;
        }
    }

    resultContent.innerHTML = html;
}

// ==================================
// 格式化答案（添加高亮）
// ==================================
function formatAnswer(answer) {
    if (!answer) return '';

    // 简单的格式化：高亮数字
    let formatted = answer.replace(/\b(\d+(\.\d+)?)\b/g, '<span class="answer-highlight">$1</span>');

    // 换行转换
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

// ==================================
// 显示澄清对话
// ==================================
function showClarification(data) {
    clarificationContext = data;

    const modal = document.getElementById('clarificationModal');
    const question = document.getElementById('clarificationQuestion');
    const optionsContainer = document.getElementById('clarificationOptions');

    question.textContent = data.clarification_question;

    // 生成选项
    optionsContainer.innerHTML = '';
    data.clarification_options.forEach((option, index) => {
        const div = document.createElement('div');
        div.className = 'clarification-option';
        div.textContent = option;
        div.dataset.value = option;
        div.onclick = function() {
            // 移除其他选中状态
            document.querySelectorAll('.clarification-option').forEach(el => {
                el.classList.remove('selected');
            });
            // 添加选中状态
            this.classList.add('selected');
            // 清空自定义输入
            document.getElementById('clarificationCustom').value = '';
        };
        optionsContainer.appendChild(div);
    });

    // 显示模态框
    modal.style.display = 'flex';

    setLoading(false);
}

// ==================================
// 提交澄清答案
// ==================================
async function submitClarification() {
    // 获取选中的选项或自定义输入
    const selected = document.querySelector('.clarification-option.selected');
    const customInput = document.getElementById('clarificationCustom').value.trim();

    const answer = selected ? selected.dataset.value : customInput;

    if (!answer) {
        alert('请选择一个选项或输入答案');
        return;
    }

    // 关闭模态框
    document.getElementById('clarificationModal').style.display = 'none';

    // 显示加载状态
    setLoading(true);

    try {
        const response = await fetch('/api/query', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: currentQuestion,
                clarification_answer: answer
            })
        });

        const data = await response.json();

        if (!data.success) {
            showError(data.error || '查询失败');
            return;
        }

        // 检查是否还需要澄清
        if (data.needs_clarification) {
            showClarification(data);
            return;
        }

        // 显示结果
        displayResults(data);

        // 刷新历史和统计
        loadHistory();
        loadStats();

    } catch (error) {
        console.error('澄清提交错误:', error);
        showError('网络错误，请检查连接');
    } finally {
        setLoading(false);
    }
}

// ==================================
// 跳过澄清
// ==================================
function skipClarification() {
    document.getElementById('clarificationModal').style.display = 'none';
    showError('已跳过澄清，无法继续处理查询');
}

// ==================================
// 复制SQL
// ==================================
function copySQL() {
    const sqlCode = document.getElementById('sqlCode');
    const text = sqlCode.textContent;

    navigator.clipboard.writeText(text).then(() => {
        const copyBtn = document.getElementById('copyBtn');
        const originalText = copyBtn.textContent;
        copyBtn.textContent = '✓ 已复制';

        setTimeout(() => {
            copyBtn.textContent = originalText;
        }, 2000);
    }).catch(err => {
        console.error('复制失败:', err);
        alert('复制失败，请手动复制');
    });
}

// ==================================
// 加载历史记录
// ==================================
async function loadHistory() {
    try {
        const response = await fetch('/api/history');
        const history = await response.json();

        const historyList = document.getElementById('historyList');

        if (!history || history.length === 0) {
            historyList.innerHTML = '<div class="history-placeholder">暂无历史记录</div>';
            return;
        }

        historyList.innerHTML = '';
        history.forEach(item => {
            const div = document.createElement('div');
            div.className = 'history-item';
            div.innerHTML = `
                <div class="history-item-title">${escapeHtml(item.question)}</div>
                <div class="history-item-time">${formatTime(item.timestamp)}</div>
            `;
            div.onclick = () => fillExample(item.question);
            historyList.appendChild(div);
        });

    } catch (error) {
        console.error('加载历史失败:', error);
    }
}

// ==================================
// 加载统计数据
// ==================================
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        document.getElementById('stat-total').textContent = stats.total_queries || '-';
        document.getElementById('stat-success').textContent =
            (stats.success_rate ? stats.success_rate + '%' : '-');
        document.getElementById('stat-clarify').textContent = stats.clarification_count || '-';
        document.getElementById('stat-time').textContent =
            (stats.avg_response_time ? stats.avg_response_time + 's' : '-');

    } catch (error) {
        console.error('加载统计失败:', error);
    }
}

// ==================================
// 工具函数
// ==================================
function fillExample(text) {
    document.getElementById('queryInput').value = text;
    document.getElementById('queryInput').focus();
}

function handleInputKeydown(event) {
    // Ctrl/Cmd + Enter 发送
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        sendQuery();
    }
}

function toggleHistory() {
    const panel = document.getElementById('historyPanel');
    historyPanelVisible = !historyPanelVisible;

    if (historyPanelVisible) {
        panel.classList.remove('collapsed');
    } else {
        panel.classList.add('collapsed');
    }
}

async function clearHistory() {
    if (!confirm('确定要清空所有历史记录吗？')) {
        return;
    }

    try {
        await fetch('/api/clear_history', { method: 'POST' });
        loadHistory();
        alert('历史记录已清空');
    } catch (error) {
        console.error('清空历史失败:', error);
        alert('操作失败');
    }
}

function openSettings() {
    document.getElementById('settingsModal').style.display = 'flex';
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

function exportResults() {
    const sql = document.getElementById('sqlCode').textContent;
    const results = document.getElementById('resultContent').innerText;
    const answer = document.getElementById('answerContent').innerText;

    const content = `
# NL2SQL 查询结果导出

## 问题
${currentQuestion}

## SQL 查询
${sql}

## 查询结果
${results}

## 自然语言答案
${answer}

---
导出时间: ${new Date().toLocaleString()}
    `.trim();

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nl2sql-result-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

function setLoading(loading) {
    const sendBtn = document.getElementById('sendBtn');
    const input = document.getElementById('queryInput');

    sendBtn.disabled = loading;
    input.disabled = loading;

    if (loading) {
        document.getElementById('sendBtnText').style.display = 'none';
        document.getElementById('sendBtnLoader').style.display = 'inline';
    } else {
        document.getElementById('sendBtnText').style.display = 'inline';
        document.getElementById('sendBtnLoader').style.display = 'none';
    }
}

function showError(message) {
    const resultContent = document.getElementById('resultContent');
    resultContent.innerHTML = `
        <div class="empty-state">
            <div class="empty-icon">❌</div>
            <div class="empty-text" style="color: #d32f2f;">${escapeHtml(message)}</div>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(timestamp) {
    if (!timestamp) return '刚刚';

    const now = new Date();
    const date = new Date(timestamp);
    const diff = now - date;

    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes}分钟前`;
    if (hours < 24) return `${hours}小时前`;
    if (days < 7) return `${days}天前`;

    return date.toLocaleDateString();
}

// 点击模态框外部关闭
window.onclick = function(event) {
    const clarModal = document.getElementById('clarificationModal');
    const settingsModal = document.getElementById('settingsModal');

    if (event.target === clarModal) {
        clarModal.style.display = 'none';
    }
    if (event.target === settingsModal) {
        settingsModal.style.display = 'none';
    }
}

// ==========================================
// 数据库管理功能
// ==========================================

let currentSwitchDBId = null;

// 页面加载时初始化数据库信息
document.addEventListener('DOMContentLoaded', function() {
    loadCurrentDatabase();
    loadDatabaseList();
});

// ==================================
// 加载当前数据库信息
// ==================================
async function loadCurrentDatabase() {
    try {
        const response = await fetch('/api/databases/current');
        const data = await response.json();

        if (data.success && data.database) {
            const db = data.database;
            document.getElementById('currentDBIcon').textContent = db.icon || '🗄️';
            document.getElementById('currentDBName').textContent = db.display_name || db.name;
        }
    } catch (error) {
        console.error('加载当前数据库失败:', error);
    }
}

// ==================================
// 加载数据库列表
// ==================================
async function loadDatabaseList() {
    try {
        const response = await fetch('/api/databases');
        const data = await response.json();

        if (data.success) {
            updateDBDropdown(data.databases, data.current);
            updateDBManagementList(data.databases, data.current);
        }
    } catch (error) {
        console.error('加载数据库列表失败:', error);
    }
}

// ==================================
// 更新下拉菜单
// ==================================
function updateDBDropdown(databases, currentId) {
    const list = document.getElementById('dbDropdownList');
    if (!list) return;

    list.innerHTML = '';

    databases.forEach(db => {
        const isCurrent = db.id === currentId;
        const div = document.createElement('div');
        div.className = `db-dropdown-item ${isCurrent ? 'current' : ''}`;
        div.onclick = () => {
            if (!isCurrent) {
                showSwitchDBConfirm(db.id, db.display_name);
            }
        };

        div.innerHTML = `
            <div class="db-dropdown-item-info">
                <div class="db-dropdown-item-icon">${db.icon || '🗄️'}</div>
                <div class="db-dropdown-item-text">
                    <div class="db-dropdown-item-name">${db.display_name}</div>
                    <div class="db-dropdown-item-meta">${db.name}</div>
                </div>
            </div>
            ${isCurrent ? '<span class="status-badge status-active">当前</span>' : ''}
        `;

        list.appendChild(div);
    });
}

// ==================================
// 更新数据库管理列表（设置面板）
// ==================================
function updateDBManagementList(databases, currentId) {
    const list = document.getElementById('dbManagementList');
    if (!list) return;

    list.innerHTML = '';

    databases.forEach(db => {
        const isCurrent = db.id === currentId;
        const div = document.createElement('div');
        div.className = `db-list-item ${isCurrent ? 'current' : ''}`;

        div.innerHTML = `
            <div class="db-list-item-header">
                <div class="db-list-item-title">
                    <span class="db-list-item-icon">${db.icon || '🗄️'}</span>
                    <span class="db-list-item-name">${db.display_name}</span>
                    ${isCurrent ? '<span class="status-badge status-active">使用中</span>' : ''}
                </div>
                <div class="db-list-item-actions">
                    ${!isCurrent ? `<button class="btn-icon" onclick="switchDatabaseFromSettings('${db.id}', '${db.display_name}')">🔄 切换</button>` : ''}
                    <button class="btn-icon" onclick="editDatabase('${db.id}')">✏️ 编辑</button>
                    ${!isCurrent && !db.is_default ? `<button class="btn-icon" onclick="deleteDatabase('${db.id}', '${db.display_name}')">🗑️ 删除</button>` : ''}
                </div>
            </div>
            <div class="db-list-item-meta">
                <div class="db-list-item-meta-item">
                    📍 ${db.host}:${db.port}
                </div>
                <div class="db-list-item-meta-item">
                    💾 ${db.name}
                </div>
            </div>
            ${db.description ? `<div class="db-list-item-description">${db.description}</div>` : ''}
        `;

        list.appendChild(div);
    });
}

// ==================================
// 切换下拉菜单
// ==================================
function toggleDBDropdown() {
    const dropdown = document.getElementById('dbDropdown');
    const btn = document.getElementById('dbSelectorBtn');

    if (dropdown.style.display === 'none') {
        dropdown.style.display = 'block';
        btn.classList.add('active');
        loadDatabaseList(); // 刷新列表
    } else {
        dropdown.style.display = 'none';
        btn.classList.remove('active');
    }
}

// 点击外部关闭下拉菜单
document.addEventListener('click', function(event) {
    const selector = document.querySelector('.db-selector-wrapper');
    const dropdown = document.getElementById('dbDropdown');

    if (selector && !selector.contains(event.target)) {
        dropdown.style.display = 'none';
        document.getElementById('dbSelectorBtn').classList.remove('active');
    }
});

// ==================================
// 显示切换确认对话框
// ==================================
function showSwitchDBConfirm(dbId, dbName) {
    currentSwitchDBId = dbId;
    document.getElementById('switchDBName').textContent = dbName;
    document.getElementById('switchDBModal').style.display = 'flex';
    document.getElementById('dbDropdown').style.display = 'none';
}

function closeSwitchDB() {
    document.getElementById('switchDBModal').style.display = 'none';
    currentSwitchDBId = null;
}

// ==================================
// 确认切换数据库
// ==================================
async function confirmSwitchDB() {
    if (!currentSwitchDBId) return;

    try {
        document.getElementById('loadingOverlay').style.display = 'flex';

        const response = await fetch('/api/databases/switch', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                database_id: currentSwitchDBId
            })
        });

        const data = await response.json();

        if (data.success) {
            // 切换成功，刷新页面
            alert('数据库切换成功！页面将重新加载。');
            location.reload();
        } else {
            alert(`切换失败：${data.error}`);
        }
    } catch (error) {
        console.error('切换数据库失败:', error);
        alert('切换失败，请检查网络连接');
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
        closeSwitchDB();
    }
}

// 从设置面板切换
function switchDatabaseFromSettings(dbId, dbName) {
    showSwitchDBConfirm(dbId, dbName);
}

// ==================================
// 打开添加数据库对话框
// ==================================
function openAddDatabase() {
    document.getElementById('addDatabaseModal').style.display = 'flex';
    document.getElementById('dbDropdown').style.display = 'none';

    // 清空表单
    document.getElementById('addDatabaseForm').reset();
    document.getElementById('testConnectionResult').style.display = 'none';
}

function closeAddDatabase() {
    document.getElementById('addDatabaseModal').style.display = 'none';
}

// ==================================
// 测试数据库连接
// ==================================
async function testDatabaseConnection() {
    const config = getFormData();
    const resultDiv = document.getElementById('testConnectionResult');

    resultDiv.style.display = 'block';
    resultDiv.className = '';
    resultDiv.innerHTML = '<span class="loading-inline"></span> 正在测试连接...';

    try {
        const response = await fetch('/api/databases/test', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config)
        });

        const data = await response.json();

        if (data.success) {
            resultDiv.className = 'success';
            resultDiv.innerHTML = `✓ ${data.message} - 找到 ${data.tables_count} 张表`;
        } else {
            resultDiv.className = 'error';
            resultDiv.innerHTML = `✗ ${data.message}`;
        }
    } catch (error) {
        resultDiv.className = 'error';
        resultDiv.innerHTML = `✗ 连接失败：${error.message}`;
    }
}

// ==================================
// 提交添加数据库
// ==================================
async function submitAddDatabase(event) {
    event.preventDefault();

    const config = getFormData();

    try {
        document.getElementById('loadingOverlay').style.display = 'flex';

        const response = await fetch('/api/databases', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(config)
        });

        const data = await response.json();

        if (data.success) {
            alert(`数据库添加成功！找到 ${data.tables_count} 张表。`);
            closeAddDatabase();
            loadDatabaseList();
        } else {
            alert(`添加失败：${data.error}`);
        }
    } catch (error) {
        console.error('添加数据库失败:', error);
        alert('添加失败，请检查网络连接');
    } finally {
        document.getElementById('loadingOverlay').style.display = 'none';
    }
}

// ==================================
// 从表单获取数据
// ==================================
function getFormData() {
    return {
        id: document.getElementById('dbId').value.trim(),
        name: document.getElementById('dbName').value.trim(),
        display_name: document.getElementById('dbDisplayName').value.trim(),
        icon: document.getElementById('dbIcon').value.trim() || '🗄️',
        description: document.getElementById('dbDescription').value.trim(),
        host: document.getElementById('dbHost').value.trim(),
        port: parseInt(document.getElementById('dbPort').value),
        user: document.getElementById('dbUser').value.trim(),
        password: document.getElementById('dbPassword').value
    };
}

// ==================================
// 编辑数据库（TODO）
// ==================================
function editDatabase(dbId) {
    alert('编辑功能开发中...');
    // TODO: 实现编辑功能
}

// ==================================
// 删除数据库
// ==================================
async function deleteDatabase(dbId, dbName) {
    if (!confirm(`确定要删除数据库 "${dbName}" 吗？此操作不可恢复。`)) {
        return;
    }

    try {
        const response = await fetch(`/api/databases/${dbId}`, {
            method: 'DELETE'
        });

        const data = await response.json();

        if (data.success) {
            alert('数据库删除成功！');
            loadDatabaseList();
        } else {
            alert(`删除失败：${data.error}`);
        }
    } catch (error) {
        console.error('删除数据库失败:', error);
        alert('删除失败，请检查网络连接');
    }
}

// ==================================
// 设置面板标签页切换
// ==================================
function switchSettingsTab(tabName) {
    // 切换标签按钮状态
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    event.target.classList.add('active');

    // 切换内容显示
    document.querySelectorAll('.settings-tab-content').forEach(content => {
        content.style.display = 'none';
    });
    document.getElementById(`settings-tab-${tabName}`).style.display = 'block';

    // 如果切换到数据库管理标签，刷新列表
    if (tabName === 'database') {
        loadDatabaseList();
    }
}

// 修改原有的 openSettings 函数，默认显示基本设置
function openSettings() {
    document.getElementById('settingsModal').style.display = 'flex';
    // 默认显示基本设置标签
    switchSettingsTab('basic');
}