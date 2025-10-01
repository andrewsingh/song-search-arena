// Admin Dashboard JavaScript

// Load stats on page load
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
});

// Load statistics
async function loadStats() {
    try {
        const response = await fetch('/admin/stats');
        const data = await response.json();

        if (response.ok) {
            document.getElementById('stat-queries').textContent = data.total_queries;
            document.getElementById('stat-systems').textContent = data.total_systems;
            document.getElementById('stat-pairs').textContent = data.total_pairs;
            document.getElementById('stat-tasks').textContent = data.total_tasks;
            document.getElementById('stat-completed').textContent = data.completed_tasks;
            document.getElementById('stat-judgments').textContent = data.total_judgments;
            document.getElementById('stat-raters').textContent = data.unique_raters;

            // Display active policy
            if (data.active_policy) {
                const policy = data.active_policy.policy_json;
                document.getElementById('policy-info').innerHTML = `
                    <strong>Version:</strong> ${policy.version}<br>
                    <strong>Retrieval Depth:</strong> ${policy.retrieval_depth_k}<br>
                    <strong>Final K:</strong> ${policy.final_k}<br>
                    <strong>Max per Artist:</strong> ${policy.max_per_artist}<br>
                    <strong>Exclude Seed Artist:</strong> ${policy.exclude_seed_artist ? 'Yes' : 'No'}<br>
                    <strong>Hash:</strong> <code>${policy.hash || 'N/A'}</code>
                `;
            }
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// File input handlers
document.getElementById('queries-file')?.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('queries-file-name').textContent = file.name;
    }
});

document.getElementById('responses-file')?.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
        document.getElementById('responses-file-name').textContent = file.name;
    }
});

// Upload queries
async function uploadQueries() {
    const fileInput = document.getElementById('queries-file');
    const textarea = document.getElementById('queries-textarea');
    const resultDiv = document.getElementById('queries-result');

    let data;

    try {
        // Try file first, then textarea
        if (fileInput.files.length > 0) {
            const text = await fileInput.files[0].text();
            data = JSON.parse(text);
        } else if (textarea.value.trim()) {
            data = JSON.parse(textarea.value);
        } else {
            showResult(resultDiv, 'Please provide queries via file or textarea', 'error');
            return;
        }

        showResult(resultDiv, 'Uploading...', 'info');

        const response = await fetch('/admin/upload/queries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showResult(resultDiv, `${result.message} (${result.count} items)`, 'success');
            if (result.errors && result.errors.length > 0) {
                showResult(resultDiv, `${result.message}\n\nErrors:\n${result.errors.join('\n')}`, 'warning');
            }
            loadStats();
        } else {
            showResult(resultDiv, `Error: ${result.message}\n${result.errors?.join('\n') || ''}`, 'error');
        }
    } catch (error) {
        showResult(resultDiv, `Error: ${error.message}`, 'error');
    }
}

// Upload responses
async function uploadResponses() {
    const fileInput = document.getElementById('responses-file');
    const textarea = document.getElementById('responses-textarea');
    const resultDiv = document.getElementById('responses-result');

    let data;

    try {
        if (fileInput.files.length > 0) {
            const text = await fileInput.files[0].text();
            data = JSON.parse(text);
        } else if (textarea.value.trim()) {
            data = JSON.parse(textarea.value);
        } else {
            showResult(resultDiv, 'Please provide responses via file or textarea', 'error');
            return;
        }

        showResult(resultDiv, 'Uploading...', 'info');

        const response = await fetch('/admin/upload/responses', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showResult(resultDiv, `${result.message} (${result.count} items)`, 'success');
            if (result.errors && result.errors.length > 0) {
                showResult(resultDiv, `${result.message}\n\nErrors:\n${result.errors.join('\n')}`, 'warning');
            }
            loadStats();
        } else {
            showResult(resultDiv, `Error: ${result.message}\n${result.errors?.join('\n') || ''}`, 'error');
        }
    } catch (error) {
        showResult(resultDiv, `Error: ${error.message}`, 'error');
    }
}

// Set policy
async function setPolicy() {
    const textarea = document.getElementById('policy-textarea');
    const resultDiv = document.getElementById('policy-result');

    try {
        if (!textarea.value.trim()) {
            showResult(resultDiv, 'Please provide policy JSON', 'error');
            return;
        }

        const data = JSON.parse(textarea.value);

        showResult(resultDiv, 'Setting policy...', 'info');

        const response = await fetch('/admin/policy/set', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (result.success) {
            showResult(resultDiv, result.message, 'success');
            loadStats();
        } else {
            showResult(resultDiv, `Error: ${result.error || result.message}`, 'error');
        }
    } catch (error) {
        showResult(resultDiv, `Error: ${error.message}`, 'error');
    }
}

// Materialize
async function materialize() {
    const targetJudgments = document.getElementById('target-judgments').value;
    const resultDiv = document.getElementById('materialize-result');

    try {
        showResult(resultDiv, 'Materializing (this may take a while)...', 'info');

        const response = await fetch('/admin/materialize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_judgments: parseInt(targetJudgments) })
        });

        const result = await response.json();

        if (result.success) {
            const msg = `${result.message}\n\nFinal lists: ${result.final_lists_created}\nPairs: ${result.pairs_created}\nTasks: ${result.tasks_created}`;
            showResult(resultDiv, msg, 'success');
            if (result.errors && result.errors.length > 0) {
                showResult(resultDiv, `${msg}\n\nWarnings:\n${result.errors.join('\n')}`, 'warning');
            }
            loadStats();
            loadProgress();
        } else {
            showResult(resultDiv, `Error: ${result.error || result.message}`, 'error');
        }
    } catch (error) {
        showResult(resultDiv, `Error: ${error.message}`, 'error');
    }
}

// Load progress grid
async function loadProgress() {
    try {
        const response = await fetch('/admin/progress');
        const data = await response.json();

        if (response.ok && data.progress) {
            renderProgressGrid(data.progress);
        }
    } catch (error) {
        console.error('Error loading progress:', error);
    }
}

// Render progress grid
function renderProgressGrid(progress) {
    const container = document.getElementById('progress-grid');

    if (progress.length === 0) {
        container.innerHTML = '<p class="help-text">No tasks available yet</p>';
        return;
    }

    // Group by pair_id
    const byPair = {};
    progress.forEach(item => {
        if (!byPair[item.pair_id]) {
            byPair[item.pair_id] = [];
        }
        byPair[item.pair_id].push(item);
    });

    let html = '<table class="progress-table"><thead><tr><th>Pair</th><th>Query</th><th>Progress</th><th>Status</th></tr></thead><tbody>';

    Object.keys(byPair).forEach(pairId => {
        const items = byPair[pairId];
        items.forEach((item, idx) => {
            const percentage = (item.collected / item.target * 100).toFixed(0);
            const statusClass = item.done ? 'done' : 'pending';
            html += `<tr>
                ${idx === 0 ? `<td rowspan="${items.length}">${pairId}</td>` : ''}
                <td>${item.query_id.substring(0, 12)}...</td>
                <td>
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: ${percentage}%"></div>
                        <span class="progress-text">${item.collected}/${item.target}</span>
                    </div>
                </td>
                <td><span class="status-badge ${statusClass}">${item.done ? 'Done' : 'Pending'}</span></td>
            </tr>`;
        });
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}

// Export data
async function exportData(type, format) {
    const resultDiv = document.getElementById('export-result');

    try {
        showResult(resultDiv, `Exporting ${type} as ${format.toUpperCase()}...`, 'info');

        const response = await fetch(`/admin/export/${type}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ format })
        });

        const result = await response.json();

        if (response.ok) {
            // Create download link
            const fileName = result.file_path.split('/').pop();
            const downloadHtml = `
                <div class="export-success">
                    <p>✓ Export successful!</p>
                    <p><strong>File:</strong> ${fileName}</p>
                    <a href="${result.url}" target="_blank" class="download-link">Download ${format.toUpperCase()}</a>
                </div>
            `;
            resultDiv.innerHTML = downloadHtml;
            resultDiv.className = 'result-message success';
            resultDiv.style.display = 'block';
        } else {
            showResult(resultDiv, `Error: ${result.error || 'Export failed'}`, 'error');
        }
    } catch (error) {
        showResult(resultDiv, `Error: ${error.message}`, 'error');
    }
}

// Helper to show result messages
function showResult(element, message, type) {
    element.className = `result-message ${type}`;
    element.textContent = message;
    element.style.display = 'block';
}
