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
            button.textContent = String(position + 1);
            button.title = `Question ${position + 1}`;
            button.classList.toggle("answered", hasAnswer);
            button.classList.toggle("flagged", flagged);
            button.classList.toggle("active", position === index);
            if (position === index) button.setAttribute("aria-current", "step");
            button.addEventListener("click", () => showQuestion(position));
            nav.appendChild(button);
        });
        answeredCount.textContent = `${answered} of ${panels.length} answered`;
    }

    function markDirty(panel) {
        dirty.add(panel.dataset.questionId);
        saveStatus.textContent = "Unsaved changes";
        const field = panel.querySelector("textarea.answer-field");
        if (field) {
            const words = field.value.trim().match(/\S+/g) || [];
            panel.querySelector(".word-count span").textContent = String(words.length);
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
            const words = field.value.trim().match(/\S+/g) || [];
            panel.querySelector(".word-count span").textContent = String(words.length);
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
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) void syncTimer();
    });
    paintTimer();

    submitForm.addEventListener("submit", async event => {
        event.preventDefault();
        if (finishing) return;
        if (!window.confirm("Submit this exam? You cannot edit answers afterward.")) return;
        submitButton.disabled = true;
        try {
            await saveAll();
            finishing = true;
            // submit() bypasses our event listener but still sends CSRF + POST.
            HTMLFormElement.prototype.submit.call(submitForm);
        } catch (error) {
            saveStatus.textContent = "Could not save; try again";
            alert("Some answers could not be saved. Check your connection and try again.");
            submitButton.disabled = false;
        }
    });
});
