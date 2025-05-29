// --- Globals ---
let reports = [];
let ownPosition = null; 
// mapOriginMgrs is now dynamically calculated to center ownPosition.
// It still represents the MGRS of the bottom-left corner of the canvas.
let mapOriginMgrs = { e100k: 'L', n100k: 'F', eastingIn100kKm: 0, northingIn100kKm: 0 }; 

const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');

const DEFAULT_MAP_DIAMETER_KM = 300;
let currentMapDiameterKm = DEFAULT_MAP_DIAMETER_KM;
let PIXELS_PER_KM = canvas.width / currentMapDiameterKm; // Recalculated when diameter changes
let MAP_VIEW_WIDTH_KM = currentMapDiameterKm;
let MAP_VIEW_HEIGHT_KM = canvas.height / PIXELS_PER_KM; // Assumes square canvas for now, or rather diameter defines width view

// MGRS 100km ruutujen kirjaimet
const EASTING_100K_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']; // Omit I, O
const NORTHING_100K_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S', 'T', 'U', 'V']; // Omit I, O

// --- Initialization ---
window.onload = () => {
    document.getElementById('reportForm').addEventListener('submit', handleReportSubmit);
    
    document.getElementById('setOwnPosBtn').addEventListener('click', setOwnPositionHandler);
    document.getElementById('updateMapSettingsBtn').addEventListener('click', updateMapSettingsHandler);
    warningRadiusKm = parseInt(document.getElementById('warningRadiusInput').value) || 100;
    alertRadiusKm = parseInt(document.getElementById('alertRadiusInput').value) || 50;

    // Initial setup:
    // 1. Set initial ownPosition from input
    const initialOwnPosRaw = document.getElementById('ownPositionInput').value.trim().toUpperCase();
    const initialParsedOwnPos = parseMGRS(initialOwnPosRaw);
    if (initialParsedOwnPos) {
        ownPosition = { raw: initialOwnPosRaw, parsed: initialParsedOwnPos, canvasPt: null };
    }
    // 2. Set initial map diameter and calculate scale
    currentMapDiameterKm = parseInt(document.getElementById('mapDiameterInput').value) || DEFAULT_MAP_DIAMETER_KM;
    PIXELS_PER_KM = canvas.width / currentMapDiameterKm;
    MAP_VIEW_WIDTH_KM = currentMapDiameterKm;
    MAP_VIEW_HEIGHT_KM = canvas.height / PIXELS_PER_KM; // If canvas not square, this is based on width's scale

    // 3. Recalculate map origin to center ownPosition (if set) and draw everything
    recalculateMapOriginAndRedraw();

    // --- Theme toggle ---
    const toggleThemeBtn = document.getElementById('toggleThemeBtn');
    toggleThemeBtn.addEventListener('click', () => {
    const isDark = document.body.classList.contains('dark');
    const newTheme = isDark ? 'light' : 'dark';
    applyTheme(newTheme);
    localStorage.setItem('theme', newTheme);
});

// Theme setup on load
const savedTheme = localStorage.getItem('theme') || 'dark';
applyTheme(savedTheme);

function applyTheme(theme) {
    document.body.classList.remove('light', 'dark');
    document.body.classList.add(theme);

    const btn = document.getElementById('toggleThemeBtn');
    btn.textContent = theme === 'dark' ? '☀️ Vaalea tila' : '🌙 Tumma tila';
}
};

// --- Event Handlers ---
function handleReportSubmit(event) {
    event.preventDefault();
    const form = event.target;
    const reportTimestamp = Date.now();

    const report = {
        id: form.elements.targetId.value.trim(),
        mgrsRaw: form.elements.mgrs.value.trim().toUpperCase(),
        direction: parseInt(form.elements.direction.value),
        altitude: form.elements.altitude.value.trim(),
        speed: form.elements.speed.value.trim(),
        count: form.elements.count.value.trim(),
        extra: form.elements.extra.value.trim(),
        timestamp: reportTimestamp, // Unique ID for the report
        parsedMgrs: null,
        canvasPt: null
    };

    report.parsedMgrs = parseMGRS(report.mgrsRaw);

    if (!report.parsedMgrs) {
        alert(`Virheellinen MGRS-muoto: ${report.mgrsRaw}. Käytä muotoa KKDD (esim. MH55).`);
        return;
    }
    
    report.canvasPt = mgrsToCanvasXY(report.parsedMgrs); 
    
    reports.push(report);
    reports.sort((a, b) => a.timestamp - b.timestamp); 

    updateReportsTable();
    redrawCanvas(); // Redraw to show new report
    form.reset(); 
    form.elements.altitude.value = "";
    form.elements.speed.value = "";
    form.elements.targetId.value = ""; 
    form.elements.mgrs.value = "";    
    form.elements.direction.value = ""; 
    form.elements.count.value = "";
    form.elements.extra.value = "";
if (ownPosition && ownPosition.canvasPt && report.canvasPt) {
    const dx = report.canvasPt.x - ownPosition.canvasPt.x;
    const dy = report.canvasPt.y - ownPosition.canvasPt.y;
    const distancePx = Math.sqrt(dx*dx + dy*dy);
    const distanceKm = distancePx / PIXELS_PER_KM;

    if (distanceKm <= alertRadiusKm) {
        alert(`⚠️ Hälytys! Maali ${report.id} on hälytyskehän (${alertRadiusKm} km) sisällä!`);
    } else if (distanceKm <= warningRadiusKm) {
        alert(`ℹ️ Varoitus: Maali ${report.id} on varoituskehän (${warningRadiusKm} km) sisällä.`);
    }
}

}

function updateMapSettingsHandler() {
    const diameterInput = document.getElementById('mapDiameterInput').value;
    const newDiameter = parseInt(diameterInput);
    if (!isNaN(newDiameter) && newDiameter >= 50 && newDiameter <= 2000) {
        currentMapDiameterKm = newDiameter;
    } else {
        alert("Virheellinen kartan halkaisija. Käytä arvoa 50-2000 km.");
        document.getElementById('mapDiameterInput').value = currentMapDiameterKm; 
    }
    
    PIXELS_PER_KM = canvas.width / currentMapDiameterKm;
    MAP_VIEW_WIDTH_KM = currentMapDiameterKm;
    MAP_VIEW_HEIGHT_KM = canvas.height / PIXELS_PER_KM; 

    recalculateMapOriginAndRedraw(); 
}

function setOwnPositionHandler() {
    warningRadiusKm = parseInt(document.getElementById('warningRadiusInput').value) || 100;
    alertRadiusKm = parseInt(document.getElementById('alertRadiusInput').value) || 50;
    
    const mgrsRaw = document.getElementById('ownPositionInput').value.trim().toUpperCase();
    const parsed = parseMGRS(mgrsRaw);
    if (parsed) {
        ownPosition = { raw: mgrsRaw, parsed: parsed, canvasPt: null };
        console.log("Oma sijainti asetettu:", ownPosition);
    } else {
        alert(`Virheellinen oman sijainnin MGRS: ${mgrsRaw}. Käytä muotoa KKDD (esim. MH55).`);
        ownPosition = null; 
    }
    recalculateMapOriginAndRedraw(); 
}

function recalculateMapOriginAndRedraw() {
    if (ownPosition && ownPosition.parsed) {
        // Calculate absolute km for own position
        const ownAbsEastingKm = EASTING_100K_LETTERS.indexOf(ownPosition.parsed.e100k) * 100 + ownPosition.parsed.eastingIn100kKm;
        const ownAbsNorthingKm = NORTHING_100K_LETTERS.indexOf(ownPosition.parsed.n100k) * 100 + ownPosition.parsed.northingIn100kKm;

        // Calculate where the map origin (bottom-left) should be in absolute km to center ownPosition
        const mapViewHalfWidthKm = MAP_VIEW_WIDTH_KM / 2;
        const mapViewHalfHeightKm = MAP_VIEW_HEIGHT_KM / 2;

        const originTargetAbsEastingKm = ownAbsEastingKm - mapViewHalfWidthKm;
        const originTargetAbsNorthingKm = ownAbsNorthingKm - mapViewHalfHeightKm;

        // Convert these absolute km for origin back to MGRS structure for mapOriginMgrs
        let e100kIdx = Math.floor(originTargetAbsEastingKm / 100);
        let n100kIdx = Math.floor(originTargetAbsNorthingKm / 100);

        // Clamp indices to prevent out-of-bounds access to letter arrays
        e100kIdx = Math.max(0, Math.min(e100kIdx, EASTING_100K_LETTERS.length - 1));
        n100kIdx = Math.max(0, Math.min(n100kIdx, NORTHING_100K_LETTERS.length - 1));
        
        mapOriginMgrs.e100k = EASTING_100K_LETTERS[e100kIdx];
        // Km part within the 100k square, snapped to 10km grid
        mapOriginMgrs.eastingIn100kKm = Math.floor((originTargetAbsEastingKm - (e100kIdx * 100)) / 10) * 10;
        if (mapOriginMgrs.eastingIn100kKm < 0) mapOriginMgrs.eastingIn100kKm = 0; // Ensure non-negative, adjust if necessary
        if (mapOriginMgrs.eastingIn100kKm >=100) mapOriginMgrs.eastingIn100kKm = 90;


        mapOriginMgrs.n100k = NORTHING_100K_LETTERS[n100kIdx];
        mapOriginMgrs.northingIn100kKm = Math.floor((originTargetAbsNorthingKm - (n100kIdx * 100)) / 10) * 10;
        if (mapOriginMgrs.northingIn100kKm < 0) mapOriginMgrs.northingIn100kKm = 0;
        if (mapOriginMgrs.northingIn100kKm >=100) mapOriginMgrs.northingIn100kKm = 90;


        console.log("Recalculated Map Origin MGRS for centering:", mapOriginMgrs);
    } else {
        // Default map origin if no own position is set (e.g., LF00)
        mapOriginMgrs = { e100k: 'L', n100k: 'F', eastingIn100kKm: 0, northingIn100kKm: 0 };
        console.log("Own position not set or invalid, using default map origin LF00 for map structure.");
    }
    redrawCanvas();
}

// --- MGRS and Coordinate Conversion ---
function parseMGRS(mgrsString) {
    if (!mgrsString || mgrsString.length !== 4) return null;
    const e100k = mgrsString[0].toUpperCase(); 
    const n100k = mgrsString[1].toUpperCase(); 
    const eastingDigit = parseInt(mgrsString[2]);
    const northingDigit = parseInt(mgrsString[3]);

    if (isNaN(eastingDigit) || eastingDigit < 0 || eastingDigit > 9 ||
        isNaN(northingDigit) || northingDigit < 0 || northingDigit > 9 ||
        !EASTING_100K_LETTERS.includes(e100k) ||
        !NORTHING_100K_LETTERS.includes(n100k)) {
        return null;
    }
    return {
        e100k: e100k,
        n100k: n100k,
        eastingIn100kKm: eastingDigit * 10, 
        northingIn100kKm: northingDigit * 10 
    };
}

function mgrsToCanvasXY(parsedMgrsPoint) {
    if (!parsedMgrsPoint || !mapOriginMgrs) return null;

    // Absolute km for the map origin (bottom-left of canvas)
    const originAbsEastingKm = EASTING_100K_LETTERS.indexOf(mapOriginMgrs.e100k) * 100 + mapOriginMgrs.eastingIn100kKm;
    const originAbsNorthingKm = NORTHING_100K_LETTERS.indexOf(mapOriginMgrs.n100k) * 100 + mapOriginMgrs.northingIn100kKm;

    // Absolute km for the target point
    const targetAbsEastingKm = EASTING_100K_LETTERS.indexOf(parsedMgrsPoint.e100k) * 100 + parsedMgrsPoint.eastingIn100kKm;
    const targetAbsNorthingKm = NORTHING_100K_LETTERS.indexOf(parsedMgrsPoint.n100k) * 100 + parsedMgrsPoint.northingIn100kKm;
    
    // Delta from map origin to target point in km
    const deltaEastingKm = targetAbsEastingKm - originAbsEastingKm;
    const deltaNorthingKm = targetAbsNorthingKm - originAbsNorthingKm;

    const canvasX = deltaEastingKm * PIXELS_PER_KM;
    const canvasY = canvas.height - (deltaNorthingKm * PIXELS_PER_KM); 

    return { x: canvasX, y: canvasY };
}


// --- Drawing Functions ---
function redrawCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawGridAndLabels(); // Grid is drawn relative to mapOriginMgrs

    if (ownPosition && ownPosition.parsed) { 
        ownPosition.canvasPt = mgrsToCanvasXY(ownPosition.parsed);
        if (ownPosition.canvasPt) {
            drawOwnPositionAndCircles(ownPosition.canvasPt);
        }
    }

    reports.forEach(report => {
        if (report.parsedMgrs) { 
             report.canvasPt = mgrsToCanvasXY(report.parsedMgrs);
        }
    });
    
    drawTargetReports();
    drawFlightPaths();
}

function drawGridAndLabels() {
    ctx.font = "10px Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    // Absolute km of the map origin (bottom-left of canvas)
    const originGridAbsEastingKm = EASTING_100K_LETTERS.indexOf(mapOriginMgrs.e100k) * 100 + mapOriginMgrs.eastingIn100kKm;
    const originGridAbsNorthingKm = NORTHING_100K_LETTERS.indexOf(mapOriginMgrs.n100k) * 100 + mapOriginMgrs.northingIn100kKm;

    // Pystyviivat (Easting)
    for (let kmOffset = 0; kmOffset <= MAP_VIEW_WIDTH_KM + 10; kmOffset += 10) { 
        const xOnCanvas = kmOffset * PIXELS_PER_KM; // x-coordinate on canvas
        const actualEastingKmAtLine = originGridAbsEastingKm + kmOffset; // Absolute MGRS easting km for this line
        
        const is100kmLine = actualEastingKmAtLine % 100 >= 0 && actualEastingKmAtLine % 100 < 10; // Check if it's at the start of a 100km block
        
        ctx.lineWidth = is100kmLine ? 1.5 : 0.5;
        ctx.strokeStyle = is100kmLine ? '#777' : '#ccc'; 
        
        ctx.beginPath();
        ctx.moveTo(xOnCanvas, 0);
        ctx.lineTo(xOnCanvas, canvas.height);
        ctx.stroke();

        if (is100kmLine && xOnCanvas >=0 && xOnCanvas <= canvas.width) {
            const currentE100kIdx = Math.floor(actualEastingKmAtLine / 100);
            if (currentE100kIdx >= 0 && currentE100kIdx < EASTING_100K_LETTERS.length) {
                 ctx.fillStyle = "black";
                 ctx.fillText(EASTING_100K_LETTERS[currentE100kIdx], xOnCanvas + (PIXELS_PER_KM * 2.5), 10); // Small offset from line
                 ctx.fillText(EASTING_100K_LETTERS[currentE100kIdx], xOnCanvas + (PIXELS_PER_KM * 2.5), canvas.height - 10);
            }
        } 
        else if (actualEastingKmAtLine % 10 === 0 && xOnCanvas >=0 && xOnCanvas <= canvas.width) { 
            const digit = Math.floor((actualEastingKmAtLine % 100) / 10);
            ctx.fillStyle = "#555";
            ctx.fillText(digit.toString(), xOnCanvas, 10);
        }
    }

    // Vaakaviivat (Northing)
    for (let kmOffset = 0; kmOffset <= MAP_VIEW_HEIGHT_KM + 10; kmOffset += 10) {
        const yOnCanvas = canvas.height - (kmOffset * PIXELS_PER_KM); // y-coordinate on canvas
        const actualNorthingKmAtLine = originGridAbsNorthingKm + kmOffset; // Absolute MGRS northing km

        const is100kmLine = actualNorthingKmAtLine % 100 >= 0 && actualNorthingKmAtLine % 100 < 10;

        ctx.lineWidth = is100kmLine ? 1.5 : 0.5;
        ctx.strokeStyle = is100kmLine ? '#777' : '#ccc';

        ctx.beginPath();
        ctx.moveTo(0, yOnCanvas);
        ctx.lineTo(canvas.width, yOnCanvas);
        ctx.stroke();
        
        if (is100kmLine && yOnCanvas >=0 && yOnCanvas <= canvas.height) {
            const currentN100kIdx = Math.floor(actualNorthingKmAtLine / 100);
            if (currentN100kIdx >= 0 && currentN100kIdx < NORTHING_100K_LETTERS.length) {
                ctx.fillStyle = "black";
                ctx.fillText(NORTHING_100K_LETTERS[currentN100kIdx], 15, yOnCanvas - (PIXELS_PER_KM * 2.5) ); 
                ctx.fillText(NORTHING_100K_LETTERS[currentN100kIdx], canvas.width - 15, yOnCanvas - (PIXELS_PER_KM * 2.5) );
            }
        }
        else if (actualNorthingKmAtLine % 10 === 0 && yOnCanvas >=0 && yOnCanvas <= canvas.height) {
            const digit = Math.floor((actualNorthingKmAtLine % 100) / 10);
            ctx.fillStyle = "#555";
            ctx.fillText(digit.toString(), 15, yOnCanvas);
        }
    }
}

function drawOwnPositionAndCircles(pt) {
    ctx.fillStyle = 'blue';
    ctx.fillRect(pt.x - 5, pt.y - 10, 10, 20); 
    ctx.strokeStyle = 'white';
    ctx.lineWidth = 1;
    ctx.strokeRect(pt.x - 5, pt.y - 10, 10, 20);

    ctx.strokeStyle = 'orange';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, warningRadiusKm * PIXELS_PER_KM, 0, 2 * Math.PI);
    ctx.stroke();

    ctx.strokeStyle = 'red';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, alertRadiusKm * PIXELS_PER_KM, 0, 2 * Math.PI);
    ctx.stroke();
}

function drawTargetReports() {
    reports.forEach(report => {
        if (!report.canvasPt) return; 
        const { x, y } = report.canvasPt;
        if (x < -10 || x > canvas.width + 10 || y < -10 || y > canvas.height + 10) return; 

        ctx.fillStyle = 'red';
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, 2 * Math.PI); 
        ctx.fill();
        ctx.fillStyle = 'black';
        ctx.font = "10px Arial";
        ctx.textAlign = "center";
        ctx.fillText(report.id, x, y - 12); 

        const directionRad = (report.direction - 90) * Math.PI / 180; 
        const arrowLength = Math.max(5, 10 * PIXELS_PER_KM); 
        const endX = x + arrowLength * Math.cos(directionRad);
        const endY = y + arrowLength * Math.sin(directionRad);

        ctx.strokeStyle = 'black';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(endX, endY);
        ctx.stroke();

        const headlen = Math.max(2, 3 * PIXELS_PER_KM); 
        const angle = Math.atan2(endY - y, endX - x);
        ctx.beginPath();
        ctx.moveTo(endX, endY);
        ctx.lineTo(endX - headlen * Math.cos(angle - Math.PI / 6), endY - headlen * Math.sin(angle - Math.PI / 6));
        ctx.moveTo(endX, endY);
        ctx.lineTo(endX - headlen * Math.cos(angle + Math.PI / 6), endY - headlen * Math.sin(angle + Math.PI / 6));
        ctx.stroke();
    });
}

function drawFlightPaths() {
    const groupedReports = reports.reduce((acc, report) => {
        if (report.canvasPt) { 
            const { x, y } = report.canvasPt;
            if (x >= -50 && x <= canvas.width + 50 && y >= -50 && y <= canvas.height + 50) { 
                if (!acc[report.id]) acc[report.id] = [];
                acc[report.id].push(report);
            }
        }
        return acc;
    }, {});

    Object.values(groupedReports).forEach(targetReports => {
        if (targetReports.length < 2) return;
        targetReports.sort((a, b) => a.timestamp - b.timestamp);
        
        const pathPoints = targetReports.map(r => r.canvasPt).filter(pt => pt !== null); 
        if (pathPoints.length < 2) return;

        for (let i = 0; i < pathPoints.length - 1; i++) {
            const p1 = pathPoints[i];
            const p2 = pathPoints[i+1];
            
            const report1 = targetReports.find(r => r.canvasPt === p1); 
            const report2 = targetReports.find(r => r.canvasPt === p2);
            if (!report1 || !report2) continue; 

            const timeDiffMinutes = (report2.timestamp - report1.timestamp) / (1000 * 60);
            
            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);

            if (timeDiffMinutes > 15) {
                ctx.setLineDash([Math.max(2,3 * PIXELS_PER_KM), Math.max(1,2 * PIXELS_PER_KM)]); 
            } else {
                ctx.setLineDash([]); 
            }
            
            const p0 = (i === 0) ? p1 : pathPoints[i-1]; 
            const p3 = (i === pathPoints.length - 2) ? p2 : pathPoints[i+2]; 
            const tension = 0.3; 
            const cp1x = p1.x + (p2.x - p0.x) * tension * 0.5; 
            const cp1y = p1.y + (p2.y - p0.y) * tension * 0.5;
            const cp2x = p2.x - (p3.x - p1.x) * tension * 0.5;
            const cp2y = p2.y - (p3.y - p1.y) * tension * 0.5;
            
            ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, p2.x, p2.y);
            ctx.strokeStyle = 'darkmagenta';
            ctx.lineWidth = 1.5;
            ctx.stroke();
        }
        ctx.setLineDash([]); 
    });
}

// --- UI Updates ---
function updateReportsTable() {
    const tbody = document.getElementById('reportsTable').getElementsByTagName('tbody')[0];
    tbody.innerHTML = ''; 

    reports.forEach(report => {
        const row = tbody.insertRow();
        const time = new Date(report.timestamp).toLocaleTimeString('fi-FI', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        row.insertCell().textContent = time;
        row.insertCell().textContent = report.id;
        row.insertCell().textContent = report.mgrsRaw;
        row.insertCell().textContent = report.direction + '°';
        row.insertCell().textContent = report.altitude;
        row.insertCell().textContent = report.speed;
        row.insertCell().textContent = report.count;
        row.insertCell().textContent = report.extra;

        const deleteCell = row.insertCell();
        const deleteButton = document.createElement('button');
        deleteButton.textContent = 'Poista';
        deleteButton.classList.add('delete-btn');
        deleteButton.onclick = () => deleteReport(report.timestamp); // Use timestamp as unique ID for deletion
        deleteCell.appendChild(deleteButton);
    });
}

function deleteReport(timestamp) {
    reports = reports.filter(r => r.timestamp !== timestamp);
    updateReportsTable(); // Update table display
    redrawCanvas(); // Redraw map without the deleted report's path/points
}

