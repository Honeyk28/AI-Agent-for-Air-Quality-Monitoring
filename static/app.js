// Modal Management Functions (Global scope so onclick can reach them)
function openModal(id) {
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById(id).classList.add('active');
}

function closeAllModals() {
    document.getElementById('modal-overlay').classList.remove('active');
    const modals = document.querySelectorAll('.custom-modal');
    modals.forEach(m => m.classList.remove('active'));
}

document.addEventListener('DOMContentLoaded', () => {
    let historyChart = null;

    // -----------------------------------------
    // 1. Setup 3D Globe
    // -----------------------------------------
    const globeContainer = document.getElementById('globeViz');
    
    // Initialize Globe
    const world = Globe()(globeContainer)
      .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-night.jpg')
      .backgroundImageUrl('https://unpkg.com/three-globe/example/img/night-sky.png')
      .showAtmosphere(true)
      .atmosphereColor('#3a228a')
      .atmosphereAltitude(0.2)
      .backgroundColor('rgba(0,0,0,0)'); // Transparent so CSS background shows

    // Set initial position (View full earth, slightly less zoomed in)
    world.pointOfView({ lat: 20, lng: 0, altitude: 2.8 });

    let isAnalyzed = false;

    // Update coordinates on globe click
    world.onGlobeClick(({ lat, lng }) => {
        if (!isAnalyzed) {
            document.getElementById('coord-lat').textContent = lat.toFixed(6);
            document.getElementById('coord-lon').textContent = lng.toFixed(6);
        }
    });

    // Auto-rotate
    world.controls().autoRotate = true;
    world.controls().autoRotateSpeed = 0.5;
    world.controls().enableZoom = true;
    world.controls().enableRotate = true;

    // Handle window resize
    window.addEventListener('resize', () => {
        world.width(window.innerWidth).height(window.innerHeight);
    });

    // -----------------------------------------
    // 2. Setup Clock
    // -----------------------------------------
    function updateClock() {
        const now = new Date();
        const str = now.toLocaleString('en-GB', { 
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        });
        document.getElementById('time-display').textContent = str.replace(',', '');
    }
    setInterval(updateClock, 1000);
    updateClock();

    // -----------------------------------------
    // 3. Form & API Handling
    // -----------------------------------------
    const cityInput = document.getElementById('city');
    const searchResults = document.getElementById('search-results');
    const apiSourceSelect = document.getElementById('api_source');
    const apiKeyInput = document.getElementById('api_key');
    const errorMsg = document.getElementById('error-message');
    const analyzeBtn = document.getElementById('analyze-btn');

    let selectedLocation = null;
    let searchTimeout = null;

    // Toggle API Key input and WAQI attribution
    apiSourceSelect.addEventListener('change', (e) => {
        const isWaqi = e.target.value === 'WAQI';
        apiKeyInput.style.display = isWaqi ? 'block' : 'none';
        document.getElementById('waqi-attribution').style.display = isWaqi ? 'block' : 'none';
    });

    // Handle Geocoding Search
    cityInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        const query = e.target.value.trim();
        
        // Hide analyze button and clear selection when user types
        analyzeBtn.style.display = 'none';
        selectedLocation = null;

        if (query.length < 2) {
            searchResults.style.display = 'none';
            return;
        }

        searchTimeout = setTimeout(async () => {
            try {
                const res = await fetch(`/api/geocode?query=${encodeURIComponent(query)}`);
                const data = await res.json();
                
                if (data.results && data.results.length > 0) {
                    searchResults.innerHTML = '';
                    data.results.forEach(loc => {
                        const div = document.createElement('div');
                        div.className = 'search-result-item';
                        div.innerHTML = `
                            <div class="result-name">${loc.name}</div>
                            <div class="result-region">${loc.admin1 ? loc.admin1 + ', ' : ''}${loc.country || ''}</div>
                        `;
                        div.onclick = () => {
                            selectedLocation = {
                                city: `${loc.name}, ${loc.admin1 ? loc.admin1 + ', ' : ''}${loc.country || ''}`,
                                lat: loc.latitude,
                                lon: loc.longitude
                            };
                            cityInput.value = selectedLocation.city;
                            searchResults.style.display = 'none';
                            isAnalyzed = false;
                            
                            // Fly to location immediately
                            updateGlobe({
                                lat: loc.latitude,
                                lon: loc.longitude,
                                city: selectedLocation.city,
                                aqi: '?',
                                color: '#3b82f6',
                                category: 'Pending'
                            });
                            
                            // Show analyze button
                            analyzeBtn.style.display = 'block';
                        };
                        searchResults.appendChild(div);
                    });
                    searchResults.style.display = 'flex';
                } else {
                    searchResults.style.display = 'none';
                }
            } catch (err) {
                console.error(err);
            }
        }, 500);
    });

    // Hide dropdown on click outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-box')) {
            searchResults.style.display = 'none';
        }
    });

    // Handle Analyze Button Click
    analyzeBtn.addEventListener('click', async () => {
        if (!selectedLocation) return;

        errorMsg.style.display = 'none';
        analyzeBtn.style.opacity = '0.5';
        analyzeBtn.disabled = true;

        const payload = {
            city: selectedLocation.city,
            lat: selectedLocation.lat,
            lon: selectedLocation.lon,
            api_source: apiSourceSelect.value,
            api_key: apiKeyInput.value.trim()
        };

        // Show right panel
        document.getElementById('agent-panel').style.display = 'block';
        document.getElementById('alert-panel').style.display = 'none';
        
        // Reset agent trace UI
        document.getElementById('agent-final-decision').style.display = 'none';
        const agentStepsContainer = document.getElementById('agent-steps');
        const defaultSteps = [
            "Location Identification",
            "Coordinates Confirmed",
            "Retrieving Air-Quality Data",
            "Analyzing Pollutants",
            "Running AQI Prediction Model",
            "Determining AQI Category",
            "Evaluating Environmental Risk",
            "Making Agent Decision",
            "Automated Alert Evaluation"
        ];
        
        // Set Status
        document.getElementById('agent-status-text').textContent = 'ANALYZING...';
        document.getElementById('agent-status-text').style.color = 'var(--accent)';
        document.getElementById('agent-spinner').style.display = 'inline-block';

        agentStepsContainer.innerHTML = defaultSteps.map((step, idx) => `
            <div class="agent-step" id="step-${idx}">
                <div class="step-icon"></div>
                <span>${step}</span>
                <span class="step-status-text" id="step-status-${idx}"></span>
            </div>
        `).join('');

        // Start simulated sequential trace animation
        let currentStep = 0;
        const totalSteps = defaultSteps.length;
        
        const nextStep = () => {
            if (currentStep > 0) {
                const prev = document.getElementById(`step-${currentStep-1}`);
                const prevStatus = document.getElementById(`step-status-${currentStep-1}`);
                if (prev) {
                    prev.classList.remove('running');
                    prev.classList.add('completed');
                    prevStatus.textContent = 'COMPLETED';
                }
            }
            if (currentStep < totalSteps) {
                const curr = document.getElementById(`step-${currentStep}`);
                const currStatus = document.getElementById(`step-status-${currentStep}`);
                if (curr) {
                    curr.classList.add('running');
                    currStatus.textContent = 'RUNNING';
                }
            }
        };

        nextStep();
        const traceInterval = setInterval(() => {
            currentStep++;
            if (currentStep < totalSteps) {
                nextStep();
            } else {
                clearInterval(traceInterval);
                nextStep(); // Complete the last step
            }
        }, 800); // 800ms delay per step for visualization

        try {
            const response = await fetch('/api/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch prediction.');
            }
            
            // Wait for trace to finish at least partially
            const waitTime = Math.max(0, (totalSteps * 800) - (currentStep * 800));
            setTimeout(() => {
                document.getElementById('agent-status-text').textContent = 'ANALYSIS COMPLETE';
                document.getElementById('agent-status-text').style.color = 'var(--c-good)';
                document.getElementById('agent-spinner').style.display = 'none';
                updateUI(data);
                updateGlobe(data); // Final update with actual color and AQI
            }, waitTime);
            
        } catch (error) {
            clearInterval(traceInterval);
            document.getElementById('agent-status-text').textContent = 'ERROR';
            document.getElementById('agent-status-text').style.color = '#ef4444';
            document.getElementById('agent-spinner').style.display = 'none';
            errorMsg.textContent = error.message;
            errorMsg.style.display = 'block';
            
            const curr = document.getElementById(`step-${currentStep}`);
            const currStatus = document.getElementById(`step-status-${currentStep}`);
            if (curr) {
                curr.classList.remove('running');
                currStatus.textContent = 'FAILED';
                currStatus.style.color = '#ef4444';
            }
        } finally {
            analyzeBtn.style.opacity = '1';
            analyzeBtn.disabled = false;
        }
    });

    // -----------------------------------------
    // 4. Update UI
    // -----------------------------------------
    function updateUI(data) {
        // Show Main Stats Panel
        const mainStatsPanel = document.getElementById('main-stats-panel');
        if (mainStatsPanel) mainStatsPanel.style.display = 'block';

        // Location & Time
        document.getElementById('loc-name').textContent = data.city;
        if(document.getElementById('data-source-display')){
            document.getElementById('data-source-display').textContent = data.data_source || 'Open-Meteo';
            if (data.data_source && data.data_source.includes('Fallback')) {
                document.getElementById('data-source-display').style.color = '#ef4444';
            } else {
                document.getElementById('data-source-display').style.color = 'var(--accent)';
            }
        }
        
        // AQI Score
        document.getElementById('aqi-score').textContent = data.aqi;
        
        // Set CSS Variables for Colors
        document.documentElement.style.setProperty('--current-aqi-color', data.color);
        const rgb = hexToRgb(data.color);
        if(rgb) {
            document.documentElement.style.setProperty('--current-aqi-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`);
        }

        // Pollutants
        document.getElementById('dom-pol').textContent = data.dominant_pollutant.toUpperCase();
        
        const pGrid = document.getElementById('pollutant-grid');
        pGrid.innerHTML = '';
        const labels = {'pm2_5': 'PM2.5', 'pm10': 'PM10', 'no2': 'NO₂', 'so2': 'SO₂', 'co': 'CO', 'o3': 'O₃'};
        for (const [key, val] of Object.entries(data.pollutants)) {
            pGrid.innerHTML += `
                <div class="p-min">
                    <span>${labels[key] || key}</span>
                    <strong style="color: white;">${Number(val).toFixed(1)}</strong>
                </div>
            `;
        }

        // Alert Panel
        document.getElementById('alert-panel').style.display = 'block';
        
        const alertStatus = document.getElementById('alert-status');
        const alertSeverity = document.getElementById('alert-severity');
        
        if (data.alert.triggered) {
            alertStatus.textContent = "TRIGGERED";
            alertStatus.style.color = "#ef4444";
            document.getElementById('alert-panel').style.border = "1px solid #ef4444";
        } else {
            alertStatus.textContent = "NOT TRIGGERED";
            alertStatus.style.color = "#10b981";
            document.getElementById('alert-panel').style.border = "1px solid rgba(255,255,255,0.08)";
        }

        const sevColors = {
            "LOW": "#10b981",
            "MODERATE": "#f59e0b",
            "HIGH": "#f97316",
            "VERY HIGH": "#ef4444",
            "CRITICAL": "#8b5cf6"
        };
        
        alertSeverity.textContent = data.alert.severity;
        alertSeverity.style.color = sevColors[data.alert.severity] || "white";
        
        document.getElementById('alert-reason').textContent = data.decision.reason;
        document.getElementById('alert-decision').textContent = data.decision.decision;
        document.getElementById('alert-recommendation').textContent = data.decision.recommendation;
        
        // Agent Explanation in Agent Panel
        document.getElementById('agent-final-decision').style.display = 'block';
        document.getElementById('agent-decision-text').textContent = data.decision.decision;

        const polMap = {'pm2_5': 'PM2.5', 'pm10': 'PM10', 'no2': 'NO₂', 'so2': 'SO₂', 'co': 'CO', 'o3': 'O₃'};
        const nicePol = polMap[data.dominant_pollutant] || data.dominant_pollutant.toUpperCase();
        
        let recText = data.decision.recommendation || "";
        recText = recText.charAt(0).toLowerCase() + recText.slice(1);
        
        document.getElementById('agent-explanation-text').textContent = 
            `${nicePol} is the dominant pollutant and the predicted AQI is ${data.aqi}, placing the location in the ${data.decision.risk_level} category. The agent therefore recommends ${recText}`;
        
        isAnalyzed = true;
        
        // Coordinates
        document.getElementById('coord-lat').textContent = Number(data.lat).toFixed(6);
        document.getElementById('coord-lon').textContent = Number(data.lon).toFixed(6);

        // Chart
        document.getElementById('chart-panel').style.display = 'block';
        updateChart(data.history, data.color);
    }

    // -----------------------------------------
    // 5. Update Globe Marker
    // -----------------------------------------
    function updateGlobe(data) {
        if(data.lat === 0 && data.lon === 0) return; // Ignore if no coords

        // Create marker data
        const marker = {
            lat: data.lat,
            lng: data.lon,
            size: 0.1,
            color: data.color,
            label: `${data.city} (AQI: ${data.aqi})`
        };

        // Pause auto-rotation temporarily to focus
        world.controls().autoRotate = false;

        // Fly to location
        world.pointOfView({
            lat: data.lat,
            lng: data.lon,
            altitude: 1.0
        }, 2000); // 2 seconds animation

        // Add rings/markers
        world
            .htmlElementsData([marker])
            .htmlElement(d => {
                const el = document.createElement('div');
                el.style.position = 'relative';
                el.style.width = '0px';
                el.style.height = '0px';
                
                el.innerHTML = `
                    <div style="
                        position: absolute;
                        bottom: 15px;
                        left: 50%;
                        transform: translateX(-50%);
                        background: rgba(20,24,32,0.8);
                        border: 1px solid rgba(255,255,255,0.2);
                        padding: 8px 12px;
                        border-radius: 8px;
                        color: white;
                        font-family: Inter, sans-serif;
                        font-size: 12px;
                        pointer-events: auto;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.5);
                        white-space: nowrap;
                    ">
                        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                            <span style="width:10px; height:10px; border-radius:50%; background:${d.color}; display:inline-block;"></span>
                            <strong>${data.city.split(',')[0]}</strong>
                        </div>
                        <span style="color: #9ca3af;">AQI: </span><span style="color:${d.color}; font-weight:bold;">${data.aqi} - ${data.category}</span>
                    </div>
                    <div style="
                        position: absolute;
                        top: -10px;
                        left: -10px;
                        width: 20px; 
                        height: 20px;
                        background: radial-gradient(circle, ${d.color} 0%, transparent 70%);
                        border-radius: 50%;
                        animation: pulse 2s infinite;
                        pointer-events: none;
                    "></div>
                `;
                return el;
            });
            
        // Resume rotation after flying
        setTimeout(() => {
            world.controls().autoRotate = true;
        }, 5000);
    }

    function updateChart(historyData, color) {
        const ctx = document.getElementById('historyChart').getContext('2d');
        const fallback = document.getElementById('chart-fallback');
        
        if (historyChart) {
            historyChart.destroy();
        }

        if (!historyData || historyData.length === 0) {
            document.getElementById('historyChart').style.display = 'none';
            fallback.style.display = 'flex';
            return;
        }

        document.getElementById('historyChart').style.display = 'block';
        fallback.style.display = 'none';

        const labels = historyData.map(d => {
            const date = new Date(d.time);
            return date.getHours() + ':00';
        });
        const values = historyData.map(d => d.aqi);

        const gradient = ctx.createLinearGradient(0, 0, 0, 140);
        const rgb = hexToRgb(color) || {r:59, g:130, b:246};
        gradient.addColorStop(0, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.5)`);
        gradient.addColorStop(1, `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.0)`);

        historyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Predicted AQI',
                    data: values,
                    borderColor: color,
                    backgroundColor: gradient,
                    borderWidth: 2,
                    pointBackgroundColor: color,
                    pointBorderColor: '#fff',
                    pointRadius: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#94a3b8' },
                        beginAtZero: false,
                        suggestedMin: Math.max(0, Math.min(...values) - 5),
                        suggestedMax: Math.max(...values) + 5
                    }
                }
            }
        });
    }

    // Helper
    function hexToRgb(hex) {
        var result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : null;
    }
});

// Add keyframes for marker pulse dynamically
const style = document.createElement('style');
style.innerHTML = `
@keyframes pulse {
    0% { transform: scale(1); opacity: 0.8; }
    50% { transform: scale(2); opacity: 0; }
    100% { transform: scale(1); opacity: 0; }
}
`;
document.head.appendChild(style);
