function getActiveDocumentInfo() {
    try {
        var doc = null;
        var info = { path: "", name: "" };

        // Check for Photoshop
        if (typeof app !== "undefined" && app.name === "Adobe Photoshop") {
            if (app.documents.length > 0) {
                doc = app.activeDocument;
                try {
                    info.path = doc.fullName.fsName;
                } catch (e) {
                    info.path = ""; // Untitled documents
                }
                info.name = doc.name;
            }
        }
        // Check for Premiere Pro
        else if (typeof app.project !== "undefined") {
            var project = app.project;
            if (project && project.path !== "") {
                info.path = project.path;
                info.name = project.name;
                // Get active sequence
                if (project.activeSequence) {
                    info.active_sequence = project.activeSequence.name;
                }
            }
        }
        // Check for Illustrator
        else if (typeof app.documents !== "undefined" && app.documents.length > 0) {
             doc = app.activeDocument;
             try {
                info.path = doc.fullName.fsName;
             } catch(e) {
                 info.path = "";
             }
             info.name = doc.name;
        }

        return JSON.stringify(info);
    } catch (err) {
        return JSON.stringify({ error: err.message });
    }
}
