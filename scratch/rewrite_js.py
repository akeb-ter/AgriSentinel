import re

with open('web/templates/dashboard.html', encoding='utf-8') as f:
    text = f.read()

# We want to replace everything from "    // 3. CAMERA & FILE HANDLING" to the start of "    // 5. SIGNAL: OVERLAY + SOUND"
# We'll use a regex
replacement_js = """
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 3. WEBSOCKET REALTIME ALERTS
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const insectName = document.getElementById('insectName');
    const insectConfidence = document.getElementById('insectConfidence');
    const insectAction = document.getElementById('insectAction');
    const resultBox = document.getElementById('resultBox');
    let alertActive = false;

    // Connect to FastAPI WebSocket
    const wsUrl = `ws://${window.location.host}/ws/alerts`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = function(event) {
        const data = JSON.parse(event.data);
        if (data.type === 'PEST_DETECTED') {
            handleDetection(data);
        }
    };

    function handleDetection(data) {
        const confidencePercent = (data.confidence * 100).toFixed(0);

        insectName.textContent = data.name;
        insectConfidence.textContent = `Confidence: ${confidencePercent}%`;
        insectAction.innerHTML = `<i class="fas fa-lightbulb" style="color:#f5a623;"></i> ${data.action}`;

        if (data.confidence > 0.85) insectConfidence.style.color = '#1f8b4c';
        else if (data.confidence > 0.70) insectConfidence.style.color = '#e67e22';
        else insectConfidence.style.color = '#c0392b';

        const isHighRisk = data.signal && data.signal.toLowerCase().includes('high');
        
        if (isHighRisk && data.confidence > 0.75) {
            resultBox.classList.add('alert');
            triggerSignal(data.name, data.action);
            addAlertLog(`🚨 ${data.name} detected! (${confidencePercent}%)`);
        } else {
            resultBox.classList.remove('alert');
            addAlertLog(`✅ ${data.name} identified (${confidencePercent}%) — Signal: ${data.signal || 'Unknown'}`);
        }
    }
"""

text = re.sub(r'// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\s*// 3\. CAMERA & FILE HANDLING.*?// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\s*// 5\. SIGNAL: OVERLAY \+ SOUND', replacement_js + '\n    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n    // 5. SIGNAL: OVERLAY + SOUND', text, flags=re.DOTALL)

# Also remove getRandomInsect()
text = re.sub(r'function getRandomInsect\(\) \{.*?\n    \}', '', text, flags=re.DOTALL)

with open('web/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(text)

