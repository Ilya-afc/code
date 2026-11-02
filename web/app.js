const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

// Fetch stats every 5 seconds
async function refreshStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        
        document.getElementById('val-checked').innerText = data.checked_count;
        document.getElementById('val-found').innerText = data.found_count;
        
        const statusEl = document.getElementById('val-status');
        statusEl.innerText = data.auto_on ? "ON" : "OFF";
        statusEl.style.color = data.auto_on ? "#00e676" : "#ff4b4b";

        renderVipList(data.watch_list);

    } catch (err) {
        console.error("Error fetching stats:", err);
    }
}

function renderVipList(list) {
    const container = document.getElementById('vip-container');
    if (!list || list.length === 0) {
        container.innerHTML = '<div class="empty-state">No names tracked</div>';
        return;
    }
    container.innerHTML = '';
    list.forEach(name => {
        const span = document.createElement('span');
        span.className = 'vip-tag';
        span.innerText = '@' + name;
        container.appendChild(span);
    });
}

function sendCommand(cmd) {
    fetch(`/api/command`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ command: cmd })
    })
    .then(res => res.json())
    .then(() => {
        setTimeout(refreshStats, 500); // Refresh after action
    });
}

// Modal Logic
function openAddModal() { document.getElementById('modal').classList.remove('hidden'); }
function closeModal() { document.getElementById('modal').classList.add('hidden'); }

function submitVip() {
    const input = document.getElementById('vip-input');
    let val = input.value.trim().replace('@','').toLowerCase();
    if(val) {
        sendCommand(`/add ${val}`);
        input.value = '';
        closeModal();
    }
}

document.getElementById('close-btn').onclick = () => tg.close();

// Initial load and interval
window.onload = () => {
    setTimeout(refreshStats, 500);
    setInterval(refreshStats, 5000);
};
