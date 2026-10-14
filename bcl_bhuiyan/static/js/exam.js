"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const app = document.getElementById("examApp");
    if (!app) return;

    const panels = Array.from(document.querySelectorAll(".question-panel"));
    const initialData = JSON.parse(document.getElementById("savedAnswersData").textContent);
    const saved = new Map(initialData.map(row => [String(row.question_id), row]));
    const dirty = new Set();
    const nav = document.getElementById("questionNav");
    const saveStatus = document.getElementById("saveStatus");
    const answeredCount = document.getElementById("answeredCount");
    const timerEl = document.getElementById("examTimer");
    const submitForm = document.getElementById("submitExamForm");
    const submitButton = document.getElementById("submitButton");
    const prevButton = document.getElementById("prevQuestion");
    const nextButton = document.getElementById("nextQuestion");
    let index = 0;
    let finishing = false;
    let syncing = false;
    let deadline = Date.now() + Number(timerEl.dataset.remaining) * 1000;
    let queue = Promise.resolve();
    const violationModal = document.getElementById("violationModal");
    const acknowledgeViolation = document.getElementById("acknowledgeViolation");
    const violationMessage = document.getElementById("violationMessage");
    let violationPending = false;
    let lastViolationAt = 0;
    let warningOpen = false;
    let submittingNormally = false;


    function getAnswer(panel) {
        const selected = panel.querySelector('input[type="radio"]:checked');
        if (selected) return selected.value;
        const field = panel.querySelector(".answer-field");
        return field ? field.value : "";
    }

    function renderNavigation() {
        nav.innerHTML = "";
        let answered = 0;
        panels.forEach((panel, position) => {
            const hasAnswer = getAnswer(panel).trim().length > 0;
            const flagged = panel.querySelector(".flag-input").checked;
            if (hasAnswer) answered += 1;
            const button = document.createElement("button");
            button.type = "button";
            const writingTask = app.classList.contains("writing-exam");
            button.textContent = writingTask ? (panel.dataset.taskLabel || `Task ${position + 1}`) : String(position + 1);
            button.title = writingTask ? button.textContent : `Question ${position + 1}`;
            button.classList.toggle("answered", hasAnswer);
            button.classList.toggle("flagged", flagged);
            button.classList.toggle("active", position === index);
            if (position === index) button.setAttribute("aria-current", "step");
            button.addEventListener("click", () => showQuestion(position));
            nav.appendChild(button);
        });
        answeredCount.textContent = `${answered} of ${panels.length} answered`;
        updateWritingTotal();
    }

    function countWords(value) {
        return (value.trim().match(/\S+/g) || []).length;
    }

    function updateWritingTotal() {
        const total = document.getElementById("writingTotalWords");
        if (!total) return;
        const words = panels.reduce((sum, panel) => {
            const editor = panel.querySelector("textarea.writing-editor");
            return sum + (editor ? countWords(editor.value) : 0);
        }, 0);
        total.textContent = `Total words: ${words}`;
    }

    function markDirty(panel) {
        dirty.add(panel.dataset.questionId);
        saveStatus.textContent = "Unsaved changes";
        const field = panel.querySelector("textarea.answer-field");
        if (field) {
            panel.querySelector(".word-count span").textContent = String(countWords(field.value));
        }
        renderNavigation();
    }

    function showQuestion(position) {
        if (position < 0 || position >= panels.length) return;
        const previous = panels[index];
        index = position;
        panels.forEach((panel, i) => { panel.hidden = i !== index; });
        prevButton.disabled = index === 0;
        nextButton.disabled = index === panels.length - 1;
        renderNavigation();
        if (previous && dirty.has(previous.dataset.questionId)) {
            void saveQuestion(previous.dataset.questionId);
        }
    }

    // Serial requests ensure the last typed answer cannot be overwritten
    // by an older response that finishes later.
    function saveQuestion(questionId) {
        if (!dirty.has(questionId) || finishing) return queue;
        const panel = panels.find(p => p.dataset.questionId === questionId);
        if (!panel) return queue;
        const answerText = getAnswer(panel);
        const isFlagged = panel.querySelector(".flag-input").checked;
        dirty.delete(questionId);
        const payload = {question_id: Number(questionId), answer_text: answerText, is_flagged: isFlagged};
        queue = queue.catch(() => {}).then(async () => {
            saveStatus.textContent = "Saving...";
            let response;
            try {
                response = await fetch(app.dataset.saveUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]').value,
                    },
                    body: JSON.stringify(payload),
                });
            } catch (error) {
                dirty.add(questionId);
                saveStatus.textContent = "Offline — unsaved changes";
                throw error;
            }
            if (!response.ok) {
                dirty.add(questionId);
                const body = await response.json().catch(() => ({}));
                saveStatus.textContent = body.error || "Save failed";
                if (response.status === 409) {
                    finishing = true;
                    window.location.replace(app.dataset.resultUrl);
                }
                throw new Error(body.error || "Unable to save answer");
            }
            const result = await response.json();
            saved.set(questionId, result);
            saveStatus.textContent = dirty.size ? "Unsaved changes" : "Saved";
        });
        return queue;
    }

    async function saveAll() {
        const ids = Array.from(dirty);
        for (const id of ids) await saveQuestion(id);
        await queue;
        if (dirty.size) throw new Error("Some changes are not saved yet.");
    }

    function formatTime(value) {
        const hours = Math.floor(value / 3600);
        const minutes = Math.floor((value % 3600) / 60);
        const seconds = value % 60;
        return [hours, minutes, seconds].map(n => String(n).padStart(2, "0")).join(":");
    }

    function paintTimer() {
        if (finishing) return;
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        timerEl.textContent = formatTime(remaining);
        timerEl.classList.toggle("warning", remaining <= 300);
        if (remaining === 0) void syncTimer();
    }

    async function syncTimer() {
        if (syncing || finishing) return;
        syncing = true;
        try {
            const response = await fetch(app.dataset.timerUrl, {credentials: "same-origin", cache: "no-store"});
            if (!response.ok) throw new Error("Timer check failed");
            const data = await response.json();
            if (data.status !== "in_progress") {
                finishing = true;
                window.location.replace(app.dataset.resultUrl);
                return;
            }
            deadline = Date.now() + data.remaining_seconds * 1000;
            paintTimer();
        } catch (error) {
            console.warn(error);
        } finally {
            syncing = false;
        }
    }

    for (const panel of panels) {
        const row = saved.get(panel.dataset.questionId);
        if (row) {
            const field = panel.querySelector(".answer-field");
            if (field) field.value = row.answer_text;
            const radios = panel.querySelectorAll('input[type="radio"]');
            radios.forEach(radio => { radio.checked = radio.value === row.answer_text; });
            panel.querySelector(".flag-input").checked = row.is_flagged;
        }
        panel.querySelectorAll("input, textarea").forEach(input => {
            input.addEventListener(input.type === "radio" || input.type === "checkbox" ? "change" : "input", () => markDirty(panel));
        });
        const field = panel.querySelector("textarea.answer-field");
        if (field) {
            panel.querySelector(".word-count span").textContent = String(countWords(field.value));
        }
    }

    document.getElementById("noQuestions").hidden = panels.length > 0;
    prevButton.addEventListener("click", () => showQuestion(index - 1));
    nextButton.addEventListener("click", () => showQuestion(index + 1));
    if (panels.length) showQuestion(0);
    else {
        prevButton.disabled = true;
        nextButton.disabled = true;
        renderNavigation();
    }

    setInterval(() => { if (!finishing) void saveAll().catch(console.warn); }, 15000);
    setInterval(paintTimer, 1000);
    setInterval(syncTimer, 10000);
    // A visibility or focus-loss report can be caused by normal browser
    // actions. These reports are indicators, not proof of dishonesty.
    async function reportViolation(reason) {
        if (finishing || submittingNormally || warningOpen || violationPending) return;
        const now = Date.now();
        // visibilitychange and blur often fire for the same action.
        if (now - lastViolationAt < 2000) return;
        lastViolationAt = now;
        violationPending = true;
        try {
            const response = await fetch(app.dataset.violationUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]').value,
                },
                body: JSON.stringify({reason}),
                keepalive: true,
            });
            const data = await response.json().catch(() => ({}));
            if (response.status === 409 || data.status === "auto_submitted") {
                finishing = true;
                window.location.replace(app.dataset.resultUrl);
                return;
            }
            if (!response.ok) throw new Error(data.error || "Unable to record focus loss");
            if (data.warning) {
                warningOpen = true;
                violationMessage.textContent = "First warning: you left the examination tab or window. A second recorded violation will automatically submit your exam.";
                violationModal.hidden = false;
                if (!document.hidden) acknowledgeViolation.focus();
            }
        } catch (error) {
            console.warn("Could not send exam focus report:", error);
            saveStatus.textContent = "Connection issue — check exam status";
        } finally {
            violationPending = false;
        }
    }

    acknowledgeViolation.addEventListener("click", () => {
        violationModal.hidden = true;
        warningOpen = false;
        acknowledgeViolation.blur();
        lastViolationAt = Date.now();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            void reportViolation("tab_hidden");
        } else {
            if (warningOpen) acknowledgeViolation.focus();
            void syncTimer();
        }
    });
    window.addEventListener("blur", () => {
        if (!document.hidden && !warningOpen) void reportViolation("window_blur");
    });
    paintTimer();

    // Reading passage tools: selections are visual only and notes are
    // stored per candidate attempt in this browser (never sent to Django).
    if (app.classList.contains("reading-exam")) {
        const storagePrefix = `ielts-notes:${app.dataset.attemptId}:`;
        const notesBySection = new Map();
        document.querySelectorAll(".passage-notes").forEach(field => {
            const sectionId = field.dataset.sectionId;
            const key = storagePrefix + sectionId;
            if (!notesBySection.has(sectionId)) {
                let value = "";
                try { value = window.localStorage.getItem(key) || ""; }
                catch (error) { console.warn("Notes unavailable in browser storage", error); }
                notesBySection.set(sectionId, value);
            }
            field.value = notesBySection.get(sectionId);
            field.addEventListener("input", () => {
                notesBySection.set(sectionId, field.value);
                document.querySelectorAll(`.passage-notes[data-section-id="${sectionId}"]`)
                    .forEach(other => { if (other !== field) other.value = field.value; });
                try { window.localStorage.setItem(key, field.value); }
                catch (error) { console.warn("Unable to store passage notes", error); }
            });
        });
        // Capture the selection before the toolbar button takes focus.
        let chosenRange = null;
        document.addEventListener("selectionchange", () => {
            const selection = window.getSelection();
            if (!selection || selection.isCollapsed || !selection.rangeCount) return;
            const range = selection.getRangeAt(0);
            const region = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
                ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
            const passage = region?.closest?.(".selectable-passage");
            if (passage && passage.closest(".question-panel")?.hidden === false) {
                chosenRange = range.cloneRange();
            }
        });
        document.querySelectorAll(".highlight-selection").forEach(button => {
            button.addEventListener("click", () => {
                const passage = button.closest(".reading-passage").querySelector(".selectable-passage");
                const range = chosenRange;
                if (!range || range.collapsed || !passage.contains(range.commonAncestorContainer)) return;
                // Limit highlights to one passage; preserve text without injecting HTML.
                const mark = document.createElement("mark");
                try {
                    mark.appendChild(range.extractContents());
                    range.insertNode(mark);
                    window.getSelection()?.removeAllRanges();
                    chosenRange = null;
                } catch (error) {
                    console.warn("Cannot highlight this selection", error);
                }
            });
        });
        document.querySelectorAll(".clear-highlights").forEach(button => {
            button.addEventListener("click", () => {
                const passage = button.closest(".reading-passage").querySelector(".selectable-passage");
                passage.querySelectorAll("mark").forEach(mark => mark.replaceWith(...mark.childNodes));
                passage.normalize();
                chosenRange = null;
            });
        });
    }

    // Listening: a user gesture is necessary because browsers normally block
    // audio autoplay after a POST -> redirect navigation. Audio controls are
    // intentionally absent, but browser-level playback is not tamper-proof.
    if (app.classList.contains("listening-exam")) {
        const audio = document.getElementById("listeningAudio");
        const start = document.getElementById("startListening");
        const status = document.getElementById("listeningStatus");
        const parts = Array.from(document.querySelectorAll(".listening-part"));
        let currentPart = 0;
        let started = false;
        let advancing = false;
        const unavailable = parts.length === 0 || parts.some(p => !p.dataset.audioUrl);
        if (unavailable) {
            start.disabled = true;
            status.textContent = "Audio not configured for every Listening part. Please contact the administrator.";
        }
        async function playPart(position) {
            if (finishing || position >= parts.length) {
                status.textContent = "Listening audio complete. You may review your answers before the exam deadline.";
                return;
            }
            const part = parts[position];
            currentPart = position;
            audio.src = part.dataset.audioUrl;
            audio.load();
            status.textContent = `Playing part ${position + 1} of ${parts.length}: ${part.dataset.title}`;
            const firstQuestion = panels.findIndex(p => p.dataset.sectionId === part.dataset.sectionId);
            if (firstQuestion >= 0) showQuestion(firstQuestion);
            try {
                await audio.play();
            } catch (error) {
                status.textContent = "Audio could not play. Check the file, sound settings or browser permissions.";
                console.error(error);
            }
        }
        start.addEventListener("click", () => {
            if (started || unavailable) return;
            started = true;
            start.disabled = true;
            start.hidden = true;
            void playPart(0);
        });
        audio.addEventListener("ended", async () => {
            if (advancing || finishing) return;
            advancing = true;
            try { await playPart(currentPart + 1); }
            finally { advancing = false; }
        });
        audio.addEventListener("error", () => {
            status.textContent = "There is a problem loading the Listening audio file. Please notify an administrator.";
        });
        // No visible native controls or page-level seek/pause actions.
        audio.controls = false;
    }

    submitForm.addEventListener("submit", async event => {
        event.preventDefault();
        if (finishing) return;
        submittingNormally = true;
        if (!window.confirm("Submit this exam? You cannot edit answers afterward.")) {
            submittingNormally = false;
            lastViolationAt = Date.now();
            return;
        }
        submitButton.disabled = true;
        try {
            await saveAll();
            submittingNormally = true;
            finishing = true;
            // submit() bypasses our event listener but still sends CSRF + POST.
            HTMLFormElement.prototype.submit.call(submitForm);
        } catch (error) {
            saveStatus.textContent = "Could not save; try again";
            alert("Some answers could not be saved. Check your connection and try again.");
            submitButton.disabled = false;
            submittingNormally = false;
        }
    });
});
