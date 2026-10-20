"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const app = document.getElementById("examApp");
    if (!app) return;
    const examHeader = document.querySelector(".exam-header");
    function syncReadingHeaderHeight() {
        if (!examHeader || !app.classList.contains("reading-exam")) return;
        document.documentElement.style.setProperty(
            "--reading-header-height",
            `${examHeader.getBoundingClientRect().height}px`
        );
    }
    syncReadingHeaderHeight();
    window.addEventListener("resize", syncReadingHeaderHeight);

    const panels = Array.from(document.querySelectorAll(".question-panel"));
    const readingLayouts = new Map();
    if (app.classList.contains("reading-exam")) {
        const sections = new Map();
        panels.forEach(panel => {
            const sectionId = panel.dataset.sectionId;
            if (!sections.has(sectionId)) sections.set(sectionId, []);
            sections.get(sectionId).push(panel);
        });
        sections.forEach((sectionPanels, sectionId) => {
            const firstPanel = sectionPanels[0];
            const layout = document.createElement("div");
            layout.className = "reading-layout";
            const passageColumn = document.createElement("div");
            passageColumn.className = "reading-passage-column";
            const questionColumn = document.createElement("div");
            questionColumn.className = "reading-question-column";
            const passage = firstPanel.querySelector(".reading-passage");
            if (passage) passageColumn.appendChild(passage);
            const sectionHeader = document.createElement("div");
            sectionHeader.className = "reading-section-header";
            const sectionTitle = firstPanel.querySelector(".section-name")?.textContent.trim();
            const sectionInstructions = firstPanel.querySelector(".instructions")?.textContent.trim();
            sectionHeader.innerHTML = `<strong>${sectionTitle || "Questions"}</strong>`;
            if (sectionInstructions) {
                const instructions = document.createElement("p");
                instructions.textContent = sectionInstructions;
                sectionHeader.appendChild(instructions);
            }
            firstPanel.querySelector(".instructions")?.remove();
            questionColumn.appendChild(sectionHeader);
            layout.append(passageColumn, questionColumn);
            firstPanel.parentElement.insertBefore(layout, firstPanel);
            sectionPanels.forEach(panel => {
                questionColumn.appendChild(panel);
                panel.querySelector(".reading-passage")?.remove();
            });
            readingLayouts.set(sectionId, layout);
        });
    }
    const initialData = JSON.parse(document.getElementById("savedAnswersData").textContent);
    const saved = new Map(initialData.map(row => [String(row.question_id), row]));
    const dirty = new Set();
    const nav = document.getElementById("questionNav");
    const partNav = document.getElementById("partNav");
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
        const blankFields = panel.querySelectorAll(".blank-input");
        if (blankFields.length) {
            return Array.from(blankFields).map(field => field.value.trim()).join(";;;");
        }
        const selected = panel.querySelector('input[type="radio"]:checked');
        if (selected) return selected.value;
        const field = panel.querySelector(".answer-field");
        return field ? field.value : "";
    }

    function renderNavigation() {
        nav.innerHTML = "";
        let answered = 0;
        const activeSectionId = panels[index]?.dataset.sectionId;
        panels.forEach((panel, position) => {
            const hasAnswer = getAnswer(panel).trim().length > 0;
            const flagged = panel.querySelector(".flag-input").checked;
            if (hasAnswer) answered += 1;
            if (app.classList.contains("reading-exam") && panel.dataset.sectionId !== activeSectionId) return;
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
        if (partNav) {
            partNav.querySelectorAll(".part-button").forEach(button => {
                button.classList.toggle("active", button.dataset.sectionId === activeSectionId);
                const sectionPanels = panels.filter(panel => panel.dataset.sectionId === button.dataset.sectionId);
                const sectionAnswered = sectionPanels.filter(panel => getAnswer(panel).trim().length > 0).length;
                const count = button.querySelector("small");
                if (count) count.textContent = `${sectionAnswered}/${sectionPanels.length}`;
            });
        }
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
        if (app.classList.contains("reading-exam")) {
            const sectionId = panels[index].dataset.sectionId;
            panels.forEach(panel => {
                panel.hidden = panel.dataset.sectionId !== sectionId;
            });
            readingLayouts.forEach((layout, id) => { layout.hidden = id !== sectionId; });
            panels[index].scrollIntoView({behavior: "smooth", block: "nearest"});
        } else {
            panels.forEach((panel, i) => { panel.hidden = i !== index; });
        }
        prevButton.disabled = index === 0;
        nextButton.disabled = index === panels.length - 1;
        renderNavigation();
        if (previous && dirty.has(previous.dataset.questionId)) {
            void saveQuestion(previous.dataset.questionId);
        }
    }

    if (partNav) {
        partNav.querySelectorAll(".part-button").forEach(button => {
            button.addEventListener("click", () => {
                const position = panels.findIndex(panel => panel.dataset.sectionId === button.dataset.sectionId);
                if (position >= 0) showQuestion(position);
            });
        });
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
        const questionNumber = panels.indexOf(panel) + 1;
        panel.dataset.questionNumber = String(questionNumber);
        const questionNumberLabel = panel.querySelector(".question-number");
        if (questionNumberLabel) questionNumberLabel.textContent = `Question ${questionNumber}`;
        const blankPrompt = panel.querySelector(".fill-blank-prompt");
        if (blankPrompt && !blankPrompt.querySelector(".blank-input")) {
            const count = Math.max(1, Number(blankPrompt.dataset.answerCount) || 1);
            let found = 0;
            const rendered = blankPrompt.textContent.split(/(_{3,})/).map(part => {
                if (!/^_{3,}$/.test(part)) return part;
                found += 1;
                const number = Number(panel.dataset.questionNumber) || found;
                return `<input class="blank-input" type="text" maxlength="20000" placeholder="[${number + found - 1}]" aria-label="Answer ${number + found - 1}">`;
            }).join("");
            blankPrompt.innerHTML = rendered;
            while (found < count) {
                found += 1;
                const number = Number(panel.dataset.questionNumber) || found;
                panel.querySelector(".fill-blank-prompt").insertAdjacentHTML("beforeend", `<input class="blank-input" type="text" maxlength="20000" placeholder="[${number + found - 1}]" aria-label="Answer ${number + found - 1}">`);
            }
        }
        const row = saved.get(panel.dataset.questionId);
        if (row) {
            const blankFields = panel.querySelectorAll(".blank-input");
            row.answer_text.split(";;;").forEach((value, position) => {
                if (blankFields[position]) blankFields[position].value = value;
            });
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
        // Capture the selection before a toolbar or context-menu action takes focus.
        let chosenRange = null;
        let chosenPassage = null;
        function captureSelection() {
            const selection = window.getSelection();
            if (!selection || selection.isCollapsed || !selection.rangeCount) return false;
            const range = selection.getRangeAt(0);
            const region = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE
                ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
            const passage = region?.closest?.(".selectable-passage");
            if (!passage) return false;
            chosenRange = range.cloneRange();
            chosenPassage = passage;
            return true;
        }
        document.addEventListener("selectionchange", captureSelection);
        document.addEventListener("mousedown", event => {
            if (!event.target.closest?.(".selectable-passage")) return;
            window.setTimeout(captureSelection, 0);
        });
        const highlightSelection = (passage, range) => {
            if (!passage || !range || range.collapsed || !passage.contains(range.commonAncestorContainer)) return;
            const mark = document.createElement("mark");
            try {
                mark.appendChild(range.extractContents());
                range.insertNode(mark);
                window.getSelection()?.removeAllRanges();
                chosenRange = null;
                chosenPassage = null;
            } catch (error) {
                console.warn("Cannot highlight this selection", error);
            }
        };
        const clearHighlights = passage => {
            if (!passage) return;
            passage.querySelectorAll("mark").forEach(mark => mark.replaceWith(...mark.childNodes));
            passage.normalize();
            chosenRange = null;
            chosenPassage = null;
        };
        document.querySelectorAll(".highlight-selection").forEach(button => {
            button.addEventListener("click", () => {
                const passage = button.closest(".reading-passage").querySelector(".selectable-passage");
                highlightSelection(passage, chosenRange);
            });
        });
        document.querySelectorAll(".clear-highlights").forEach(button => {
            button.addEventListener("click", () => {
                const passage = button.closest(".reading-passage").querySelector(".selectable-passage");
                clearHighlights(passage);
            });
        });
        const menu = document.createElement("div");
        menu.className = "reading-context-menu";
        menu.hidden = true;
        menu.innerHTML = '<button type="button" data-action="highlight">Highlight</button><button type="button" data-action="clear">Clear highlights</button>';
        document.body.appendChild(menu);
        const closeMenu = () => { menu.hidden = true; };
        document.addEventListener("click", event => {
            if (!menu.contains(event.target)) closeMenu();
        });
        document.addEventListener("scroll", closeMenu, true);
        document.addEventListener("contextmenu", event => {
            const passage = event.target.closest?.(".selectable-passage");
            if (!passage) return;
            event.preventDefault();
            captureSelection();
            chosenPassage = passage;
            menu.hidden = false;
            menu.style.left = `${Math.min(event.clientX, window.innerWidth - 190)}px`;
            menu.style.top = `${Math.min(event.clientY, window.innerHeight - 90)}px`;
        });
        menu.addEventListener("click", event => {
            const action = event.target.dataset.action;
            if (action === "highlight") highlightSelection(chosenPassage, chosenRange);
            if (action === "clear") clearHighlights(chosenPassage);
            closeMenu();
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
