(function () {
    const csInterface = new CSInterface();
    const API_URL = "http://127.0.0.1:10101/api/v1/context/app";
    const POLL_INTERVAL = 5000; // 5 seconds

    function getAppData() {
        const env = csInterface.getHostEnvironment();
        const appName = env.appName;
        
        // Execute ExtendScript to get active document info
        csInterface.evalScript('getActiveDocumentInfo()', function (result) {
            try {
                const docInfo = JSON.parse(result);
                if (docInfo && (docInfo.path || docInfo.name)) {
                    sendPayload({
                        app_name: mapAppIdToName(appName),
                        active_file_path: docInfo.path || null,
                        active_file_name: docInfo.name || null,
                        active_sequence: docInfo.active_sequence || null,
                        captured_at: new Date().toISOString()
                    });
                }
            } catch (e) {
                // Silently handle cases where no document is open or script fails
            }
        });
    }

    function mapAppIdToName(appId) {
        const mapping = {
            "PHSP": "Adobe Photoshop",
            "PPRO": "Adobe Premiere Pro",
            "AEFT": "Adobe After Effects",
            "ILST": "Adobe Illustrator"
        };
        return mapping[appId] || appId;
    }

    function sendPayload(data) {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", API_URL, true);
        xhr.setRequestHeader("Content-Type", "application/json");
        xhr.onreadystatechange = function () {
            if (xhr.readyState === 4) {
                // Done - silent log
            }
        };
        xhr.send(JSON.stringify(data));
    }

    // Start polling
    setInterval(getAppData, POLL_INTERVAL);
    getAppData(); // Run once immediately

    console.log("[ProductivityTracker] Adobe plugin initialized.");
})();
