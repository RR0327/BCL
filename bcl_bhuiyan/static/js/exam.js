"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const app = document.getElementById("examApp");
    if (!app) return;

    const isReading = app.classList.contains("reading-exam");
    const isListening = app.classList.contains("listening-exam");
    const isWriting = app.classList.contains("writing-exam");

    // Theme Management (Light / Dark / Device)
    const themeToggleBtn = document.getElementById("themeToggleBtn");
    const THEME_ICONS = {
        light: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-amber-500"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>`,
        dark: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-indigo-400"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>`,
        device: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-slate-600 dark:text-slate-300"><rect width="20" height="14" x="2" y="3" rx="2"></rect><line x1="8" x2="16" y1="21" y2="21"></line><line x1="12" x2="12" y1="17" y2="21"></line></svg>`
    };
    const THEME_LABELS = {
        light: { title: "Theme: Light (click for Dark)", aria: "Theme mode: Light" },
        dark: { title: "Theme: Dark (click for Device)", aria: "Theme mode: Dark" },
        device: { title: "Theme: Device / System (click for Light)", aria: "Theme mode: Device default" }
    };

    function applyTheme(theme) {
        const isDark = (theme === "dark") || (theme === "device" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
        if (isDark) {
            document.documentElement.classList.add("dark");
            document.documentElement.setAttribute("data-theme", "dark");
        } else {
            document.documentElement.classList.remove("dark");
            document.documentElement.setAttribute("data-theme", "light");
        }
    }

    function updateThemeUI(theme) {
        applyTheme(theme);
        if (!themeToggleBtn) return;
        themeToggleBtn.innerHTML = THEME_ICONS[theme] || THEME_ICONS.device;
        const meta = THEME_LABELS[theme] || THEME_LABELS.device;
        themeToggleBtn.title = meta.title;
        themeToggleBtn.setAttribute("aria-label", meta.aria);
    }

    function initTheme() {
        try {
            const savedTheme = localStorage.getItem("test-theme") || "device";
            updateThemeUI(savedTheme);
        } catch (e) {
            console.warn("Theme storage unavailable", e);
            updateThemeUI("device");
        }
    }
    initTheme();

    if (window.matchMedia) {
        const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        const handleMediaChange = () => {
            try {
                const currentTheme = localStorage.getItem("test-theme") || "device";
                if (currentTheme === "device") {
                    applyTheme("device");
                }
            } catch (e) {}
        };
        if (mediaQuery.addEventListener) {
            mediaQuery.addEventListener("change", handleMediaChange);
        } else if (mediaQuery.addListener) {
            mediaQuery.addListener(handleMediaChange);
        }
    }

    if (themeToggleBtn) {
        themeToggleBtn.addEventListener("click", () => {
            try {
                const currentTheme = localStorage.getItem("test-theme") || "device";
                const nextTheme = currentTheme === "light" ? "dark" : (currentTheme === "dark" ? "device" : "light");
                localStorage.setItem("test-theme", nextTheme);
                localStorage.setItem("theme", nextTheme === "device" ? "auto" : nextTheme);
                updateThemeUI(nextTheme);
            } catch (e) {
                console.warn("Could not save theme", e);
            }
        });
    }

    // Answers, dirty tracking, and state
    const initialData = JSON.parse(document.getElementById("savedAnswersData")?.textContent || "[]");
    const saved = new Map(initialData.map(row => [String(row.question_id), row]));
    const dirty = new Set();
    let queue = Promise.resolve();
    let finishing = false;
    let syncing = false;

    const panels = Array.from(document.querySelectorAll(".question-panel"));
    const saveStatus = document.getElementById("saveStatus");
    const timerEl = document.getElementById("examTimer");
    const submitForm = document.getElementById("submitExamForm");
    const submitBtnFooter = document.getElementById("submitExamBtn");
    const saveBtnFooter = document.getElementById("saveExamBtn");
    const headerBackBtn = document.getElementById("headerBackBtn") || document.querySelector(".back-link");
    const violationModal = document.getElementById("violationModal");
    const acknowledgeViolation = document.getElementById("acknowledgeViolation");
    const violationMessage = document.getElementById("violationMessage");

    let deadline = Date.now() + Number(timerEl?.dataset.remaining || 3600) * 1000;
    let violationPending = false;
    let lastViolationAt = 0;
    let warningOpen = false;
    let submittingNormally = false;

    // Helper: Count words
    function countWords(value) {
        return (value.trim().match(/\S+/g) || []).length;
    }

    // Helper: Read answer value from question panel
    function getAnswer(panel) {
        const blankFields = panel.querySelectorAll(".blank-input");
        if (blankFields.length) {
            return Array.from(blankFields).map(f => f.value.trim()).join(";;;");
        }
        const selected = panel.querySelector('input[type="radio"]:checked');
        if (selected) return selected.value;
        const matchingField = panel.querySelector(".matching-field");
        if (matchingField) return matchingField.value;
        const checkboxes = panel.querySelectorAll('input[type="checkbox"]:not(.flag-input):checked');
        if (checkboxes.length) {
            return Array.from(checkboxes).map(c => c.value).join(";;;");
        }
        const field = panel.querySelector(".answer-field");
        return field ? field.value : "";
    }

    // Helper: Mark question dirty and update UI
    function markDirty(panel) {
        dirty.add(panel.dataset.questionId);
        if (saveStatus) saveStatus.textContent = "Unsaved changes";
        const editor = panel.querySelector("textarea.writing-editor");
        if (editor) {
            const countEl = panel.querySelector(".word-count span");
            if (countEl) countEl.textContent = String(countWords(editor.value));
            updateWritingTotal();
        }
        updatePillsState();
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

    // Save individual question
    function saveQuestion(questionId) {
        if (!dirty.has(questionId) || finishing) return queue;
        const panel = panels.find(p => p.dataset.questionId === questionId);
        if (!panel) return queue;
        const answerText = getAnswer(panel);
        const isFlagged = Boolean(panel.querySelector(".flag-input")?.checked);
        dirty.delete(questionId);

        const payload = { question_id: Number(questionId), answer_text: answerText, is_flagged: isFlagged };
        queue = queue.catch(() => {}).then(async () => {
            if (saveStatus) saveStatus.textContent = "Saving...";
            let response;
            try {
                response = await fetch(app.dataset.saveUrl, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "",
                    },
                    body: JSON.stringify(payload),
                });
            } catch (error) {
                dirty.add(questionId);
                if (saveStatus) saveStatus.textContent = "Offline — unsaved changes";
                throw error;
            }
            if (!response.ok) {
                dirty.add(questionId);
                const body = await response.json().catch(() => ({}));
                if (saveStatus) saveStatus.textContent = body.error || "Save failed";
                if (response.status === 409) {
                    finishing = true;
                    window.location.replace(app.dataset.endedUrl || app.dataset.resultUrl);
                }
                throw new Error(body.error || "Unable to save answer");
            }
            const result = await response.json();
            saved.set(questionId, result);
            if (saveStatus) saveStatus.textContent = dirty.size ? "Unsaved changes" : "Saved";
        });
        return queue;
    }

    async function saveAll() {
        const ids = Array.from(dirty);
        for (const id of ids) await saveQuestion(id);
        await queue;
        if (dirty.size) throw new Error("Some changes are not saved yet.");
    }

    // Timer logic
    function formatTime(value) {
        const hours = Math.floor(value / 3600);
        const minutes = Math.floor((value % 3600) / 60);
        const seconds = value % 60;
        return [hours, minutes, seconds].map(n => String(n).padStart(2, "0")).join(":");
    }

    function paintTimer() {
        if (finishing || !timerEl) return;
        const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
        timerEl.textContent = formatTime(remaining);
        timerEl.classList.toggle("warning", remaining <= 300);
        if (remaining === 0) void syncTimer();
    }

    async function syncTimer() {
        if (syncing || finishing || !app.dataset.timerUrl) return;
        syncing = true;
        try {
            const response = await fetch(app.dataset.timerUrl, { credentials: "same-origin", cache: "no-store" });
            if (!response.ok) throw new Error("Timer check failed");
            const data = await response.json();
            if (data.status !== "in_progress") {
                finishing = true;
                window.location.replace(app.dataset.endedUrl || app.dataset.resultUrl);
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

    // =========================================================================
    // READING & LISTENING EXAM WORKSPACE LOGIC
    // =========================================================================
    let switchPart = null;
    let activeSectionIndex = 0;

    if (isReading || isListening) {
        // 1. Column Resizer (Reading only: Left Passage vs Right Questions)
        if (isReading) {
            const resizer = document.getElementById("splitResizer");
            const passageCol = document.getElementById("passageCol");
            const questionsCol = document.getElementById("questionsCol");
            const splitArea = document.getElementById("readingSplitArea");

            if (resizer && passageCol && questionsCol && splitArea) {
                let isResizing = false;
                resizer.addEventListener("mousedown", () => {
                    isResizing = true;
                    resizer.classList.add("is-dragging");
                    document.body.style.cursor = "col-resize";
                    document.body.style.userSelect = "none";
                });

                document.addEventListener("mousemove", (e) => {
                    if (!isResizing) return;
                    const containerRect = splitArea.getBoundingClientRect();
                    const offset = e.clientX - containerRect.left;
                    const percentage = (offset / containerRect.width) * 100;
                    if (percentage >= 25 && percentage <= 75) {
                        passageCol.style.width = `${percentage}%`;
                        questionsCol.style.width = `${100 - percentage}%`;
                    }
                });

                document.addEventListener("mouseup", () => {
                    if (isResizing) {
                        isResizing = false;
                        resizer.classList.remove("is-dragging");
                        document.body.style.cursor = "";
                        document.body.style.userSelect = "";
                    }
                });
            }
        }

        // 2. Part / Section Groups
        const sectionGroups = Array.from(document.querySelectorAll(".exam-section-group"));
        const partButtons = Array.from(document.querySelectorAll(".part-tab-button"));
        const activePassageBadge = document.getElementById("activePassageBadge");
        const activePassageTitle = document.getElementById("activePassageTitle");
        const activePassageByline = document.getElementById("activePassageByline");
        const activePassageText = document.getElementById("activePassageText");
        const activePartPillLabel = document.getElementById("activePartPillLabel");
        const questionNavPills = document.getElementById("questionNavPills");
        activeSectionIndex = 0;

        const notesStorageKey = (sectionId) => `ielts_notes_${app.dataset.attemptId}_${sectionId}`;
        const notesTextarea = document.getElementById("readingPassageNotes");

        function restorePassageNotes(sectionId) {
            if (!notesTextarea) return;
            try {
                notesTextarea.value = localStorage.getItem(notesStorageKey(sectionId)) || "";
            } catch (e) {}
        }

        // Parse and render passage paragraphs with paragraph letters (A, B, C...)
        function formatPassageParagraphs(rawText) {
            if (!rawText) return "";
            const paragraphs = rawText.split(/\n\s*\n/);
            return paragraphs.map((p) => {
                const trimmed = p.trim();
                const matchLetter = trimmed.match(/^([A-H])(?:\s*[\.\:\-\–\—\)]\s*|\s+|\b|(?=[A-Z]))(.*)$/s);
                if (matchLetter) {
                    const letter = matchLetter[1];
                    const content = matchLetter[2];
                    return `<div class="para-block" id="para-${letter}"><p class="text-[15.5px] leading-[1.9] text-gray-800 dark:text-[#E1E1E1] tracking-[0.01em]"><span class="para-letter font-extrabold text-indigo-700 dark:text-indigo-400 mr-2">${letter}</span><span>${content.trim()}</span></p></div>`;
                }
                return `<div class="para-block"><p class="text-[15.5px] leading-[1.9] text-gray-800 dark:text-[#E1E1E1] tracking-[0.01em]">${trimmed}</p></div>`;
            }).join("");
        }

        // Switch Exam Part (Passage / Part 1, 2, 3, 4)
        switchPart = function(partIndex) {
            if (partIndex < 0 || partIndex >= sectionGroups.length) return;
            activeSectionIndex = partIndex;
            const targetGroup = sectionGroups[partIndex];
            const sectionId = targetGroup.dataset.sectionId;
            const partNum = partIndex + 1;

            if (isReading) {
                if (activePassageBadge) activePassageBadge.textContent = `Passage ${partNum}`;
                if (activePassageTitle) activePassageTitle.textContent = targetGroup.dataset.sectionTitle || `Passage ${partNum}`;
                if (activePassageByline) activePassageByline.textContent = targetGroup.dataset.sectionByline || "Read the text and answer questions";

                const rawSource = targetGroup.querySelector(".passage-raw-source")?.textContent || "";
                if (activePassageText) {
                    activePassageText.innerHTML = formatPassageParagraphs(rawSource);
                }
                if (typeof restorePassageNotes === "function") {
                    restorePassageNotes(sectionId);
                }
            }

            // Show questions for this group, hide others
            sectionGroups.forEach((g, idx) => {
                g.hidden = idx !== partIndex;
            });

            // Update part tabs in footer
            partButtons.forEach((btn, idx) => {
                btn.classList.toggle("active", idx === partIndex);
            });

            if (activePartPillLabel) {
                activePartPillLabel.textContent = `Part ${partNum}`;
            }

            // Re-render Question Pills for active part
            renderPillsForActivePart();

            // Scroll questions container to top
            if (isReading) {
                document.getElementById("questionsScrollArea")?.scrollTo({ top: 0, behavior: "smooth" });
            } else if (isListening) {
                document.getElementById("listeningScrollArea")?.scrollTo({ top: 0, behavior: "smooth" });
                if (typeof window.onListeningPartSwitched === "function") {
                    window.onListeningPartSwitched(partIndex);
                }
            }
        };

        // Render Question Pills in footer for active part
        function renderPillsForActivePart() {
            if (!questionNavPills) return;
            questionNavPills.innerHTML = "";
            const currentGroup = sectionGroups[activeSectionIndex];
            if (!currentGroup) return;

            const groupPanels = Array.from(currentGroup.querySelectorAll(".question-panel"));
            groupPanels.forEach((panel, pIdx) => {
                const baseQNum = Number(panel.dataset.globalQuestionNumber) || (pIdx + 1);
                const blankPrompt = panel.querySelector(".fill-blank-prompt");
                const blankInputs = panel.querySelectorAll(".blank-input");
                const count = blankPrompt ? Math.max(1, blankInputs.length || Number(panel.dataset.answerCount) || Number(blankPrompt.dataset.answerCount) || (blankPrompt.textContent.match(/_{3,}/g) || []).length) : 1;

                if (blankPrompt && count > 1) {
                    for (let bIdx = 0; bIdx < count; bIdx++) {
                        const qNum = String(baseQNum + bIdx);
                        const btn = document.createElement("button");
                        btn.type = "button";
                        btn.className = "q-pill";
                        btn.textContent = qNum;
                        btn.title = `Question ${qNum}`;
                        btn.dataset.questionId = panel.dataset.questionId;
                        btn.dataset.blankIndex = String(bIdx);

                        const inputs = panel.querySelectorAll(".blank-input");
                        const hasAnswer = Boolean(inputs[bIdx] && inputs[bIdx].value.trim().length > 0);
                        const isFlagged = Boolean(panel.querySelector(".flag-input")?.checked);
                        btn.classList.toggle("answered", hasAnswer);
                        btn.classList.toggle("flagged", isFlagged);
                        if (pIdx === 0 && bIdx === 0) btn.classList.add("active");

                        btn.addEventListener("click", () => {
                            const currentInputs = panel.querySelectorAll(".blank-input");
                            if (currentInputs[bIdx]) {
                                currentInputs[bIdx].scrollIntoView({ behavior: "smooth", block: "center" });
                                currentInputs[bIdx].focus();
                            } else {
                                panel.scrollIntoView({ behavior: "smooth", block: "start" });
                            }
                            highlightActivePill(btn);
                        });

                        questionNavPills.appendChild(btn);
                    }
                    return;
                }

                const msCount = (panel.dataset.questionType === "multi_select") ? (Number(panel.dataset.answerCount) || 1) : 1;
                if (msCount > 1) {
                    for (let mIdx = 0; mIdx < msCount; mIdx++) {
                        const qNum = String(baseQNum + mIdx);
                        const btn = document.createElement("button");
                        btn.type = "button";
                        btn.className = "q-pill";
                        btn.textContent = qNum;
                        btn.title = `Question ${qNum}`;
                        btn.dataset.questionId = panel.dataset.questionId;
                        btn.dataset.msIndex = String(mIdx);

                        const checkboxes = panel.querySelectorAll('input[type="checkbox"]:not(.flag-input):checked');
                        const hasAnswer = (checkboxes.length >= mIdx + 1);
                        const isFlagged = Boolean(panel.querySelector(".flag-input")?.checked);
                        btn.classList.toggle("answered", hasAnswer);
                        btn.classList.toggle("flagged", isFlagged);
                        if (pIdx === 0 && mIdx === 0) btn.classList.add("active");

                        btn.addEventListener("click", () => {
                            panel.scrollIntoView({ behavior: "smooth", block: "start" });
                            highlightActivePill(btn);
                        });

                        questionNavPills.appendChild(btn);
                    }
                    return;
                }

                const qNum = panel.dataset.globalQuestionNumber || panel.querySelector(".q-number-badge")?.textContent.trim();
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "q-pill";
                btn.textContent = qNum;
                btn.title = `Question ${qNum}`;
                btn.dataset.questionId = panel.dataset.questionId;

                const hasAnswer = getAnswer(panel).trim().length > 0;
                const isFlagged = Boolean(panel.querySelector(".flag-input")?.checked);
                btn.classList.toggle("answered", hasAnswer);
                btn.classList.toggle("flagged", isFlagged);
                if (pIdx === 0) btn.classList.add("active");

                btn.addEventListener("click", () => {
                    panel.scrollIntoView({ behavior: "smooth", block: "start" });
                    highlightActivePill(btn);
                });

                questionNavPills.appendChild(btn);
            });
        }

        function highlightActivePill(activeBtn) {
            questionNavPills?.querySelectorAll(".q-pill").forEach(p => p.classList.remove("active"));
            activeBtn?.classList.add("active");
        }

        // Part buttons click handler
        partButtons.forEach((btn, idx) => {
            btn.addEventListener("click", () => switchPart(idx));
        });

        // Passage Highlighting & Notes (Reading only)
        if (isReading) {
            if (notesTextarea) {
                notesTextarea.addEventListener("input", () => {
                    const currentGroup = sectionGroups[activeSectionIndex];
                    if (!currentGroup) return;
                    try {
                        localStorage.setItem(notesStorageKey(currentGroup.dataset.sectionId), notesTextarea.value);
                    } catch (e) {}
                });
            }

            const highlightBtn = document.querySelector(".highlight-selection");
            const clearBtn = document.querySelector(".clear-highlights");

            function highlightSelection() {
                const selection = window.getSelection();
                if (!selection || selection.isCollapsed || !selection.rangeCount) return;
                const range = selection.getRangeAt(0);
                if (!activePassageText || !activePassageText.contains(range.commonAncestorContainer)) return;
                const mark = document.createElement("mark");
                try {
                    mark.appendChild(range.extractContents());
                    range.insertNode(mark);
                    selection.removeAllRanges();
                } catch (e) {
                    console.warn("Could not highlight selection", e);
                }
            }

            function clearAllHighlights() {
                if (!activePassageText) return;
                activePassageText.querySelectorAll("mark").forEach(mark => {
                    mark.replaceWith(...mark.childNodes);
                });
                activePassageText.normalize();
            }

            if (highlightBtn) highlightBtn.addEventListener("click", highlightSelection);
            if (clearBtn) clearBtn.addEventListener("click", clearAllHighlights);
        }

        // Calculate and assign global question numbers
        let globalCounter = 1;
        sectionGroups.forEach(group => {
            group.querySelectorAll(".question-panel").forEach(panel => {
                panel.dataset.globalQuestionNumber = String(globalCounter);
                const badge = panel.querySelector(".q-number-badge");
                if (badge) badge.textContent = String(globalCounter);
                const inlineNum = panel.querySelector(".q-num-inline");
                if (inlineNum) inlineNum.textContent = String(globalCounter) + ".";
                
                const blankPrompt = panel.querySelector(".fill-blank-prompt");
                if (blankPrompt) {
                    const matches = blankPrompt.textContent.match(/_{3,}/g) || [];
                    const count = Math.max(1, Number(panel.dataset.answerCount) || Number(blankPrompt.dataset.answerCount) || matches.length);
                    globalCounter += count;
                } else if (panel.dataset.questionType === "multi_select" && (Number(panel.dataset.answerCount) || 1) > 1) {
                    const msCount = Number(panel.dataset.answerCount) || 1;
                    if (inlineNum) inlineNum.textContent = `${globalCounter}–${globalCounter + msCount - 1}.`;
                    globalCounter += msCount;
                } else {
                    globalCounter += 1;
                }
            });
        });

        function setupPanelsAndAnswers() {
            panels.forEach((panel, position) => {
                const qNum = panel.dataset.globalQuestionNumber || String(position + 1);
                panel.dataset.questionNumber = qNum;

                // Fill-in-the-blank / Summary Completion formatting matching Image 5
                const blankPrompt = panel.querySelector(".fill-blank-prompt");
                if (blankPrompt && !blankPrompt.querySelector(".blank-input")) {
                    const count = Math.max(1, Number(panel.dataset.answerCount) || Number(blankPrompt.dataset.answerCount) || 1);
                    const container = panel.querySelector(".fill-blank-container");
                    const rawText = container?.dataset?.rawPrompt || blankPrompt.textContent;
                    
                    // Normalize text: fix encoding diamonds, Windows CRLF, and newlines before blanks
                    let clean = rawText
                        .replace(/\ufffd/g, "•")
                        .replace(/\r\n/g, "\n")
                        .replace(/\r/g, "\n");
                    
                    // Fix newlines around blanks or orphan bullets
                    clean = clean.replace(/([^\n])\n(\s*_{3,})/g, "$1 $2");
                    clean = clean.replace(/(_{3,})\n(\s*[a-zA-Z0-9])/g, "$1 $2");
                    clean = clean.replace(/([•\-]|•)\s*\n\s*/g, "• ");

                    const rawLines = clean.split("\n").map(l => l.trim()).filter(Boolean);
                    let html = "";
                    let found = 0;
                    let startIndex = 0;

                    // Check if first line is a Title (e.g. "Baobabs Under Threat")
                    if (rawLines.length > 0) {
                        const first = rawLines[0];
                        const isTitle = !first.includes("___") && !first.startsWith("•") && !first.startsWith("-") && first.length < 80;
                        if (isTitle) {
                            html += `<h3 class="text-base sm:text-lg font-bold text-slate-800 dark:text-white text-center pb-3 border-b border-slate-100 dark:border-zinc-700/60 mb-5">${first}</h3>`;
                            startIndex = 1;
                        }
                    }

                    for (let i = startIndex; i < rawLines.length; i++) {
                        let line = rawLines[i];
                        const hasBlank = /_{3,}/.test(line);
                        let isBullet = line.startsWith("•") || line.startsWith("- ");
                        if (isBullet) {
                            line = line.replace(/^[•\-]\s*/, "");
                        }

                        // Replace blanks with underline inputs
                        if (hasBlank) {
                            line = line.replace(/_{3,}/g, () => {
                                found += 1;
                                const blankNum = Number(qNum) + found - 1;
                                return `<input class="blank-input" type="text" maxlength="200" placeholder="[${blankNum}]" aria-label="Answer ${blankNum}">`;
                            });
                        }

                        const isSubheading = !isBullet && !hasBlank && (line.endsWith(":") || line.length < 50);

                        if (isSubheading) {
                            html += `<div class="font-bold text-slate-800 dark:text-white text-sm sm:text-base mt-4 mb-2">${line}</div>`;
                        } else if (isBullet || hasBlank) {
                            html += `<div class="my-2.5 flex items-baseline gap-2 text-slate-700 dark:text-slate-200 text-sm sm:text-base leading-relaxed"><span class="text-slate-400 font-bold select-none shrink-0">•</span><span>${line}</span></div>`;
                        } else {
                            html += `<div class="my-2 text-slate-700 dark:text-slate-200 text-sm sm:text-base leading-relaxed">${line}</div>`;
                        }
                    }

                    while (found < count) {
                        found += 1;
                        const blankNum = Number(qNum) + found - 1;
                        html += `<div class="my-2"><input class="blank-input" type="text" maxlength="200" placeholder="[${blankNum}]" aria-label="Answer ${blankNum}"></div>`;
                    }

                    blankPrompt.innerHTML = html;
                }

                // Restore saved answer
                const row = saved.get(panel.dataset.questionId);
                if (row) {
                    const blankFields = panel.querySelectorAll(".blank-input");
                    if (blankFields.length) {
                        row.answer_text.split(";;;").forEach((val, idx) => {
                            if (blankFields[idx]) blankFields[idx].value = val;
                        });
                    }
                    const matchingField = panel.querySelector(".matching-field");
                    if (matchingField) matchingField.value = row.answer_text;

                    const radios = panel.querySelectorAll('input[type="radio"]');
                    radios.forEach(radio => { radio.checked = (radio.value === row.answer_text); });

                    const checkboxes = panel.querySelectorAll('input[type="checkbox"]:not(.flag-input)');
                    if (checkboxes.length) {
                        const checkedValues = row.answer_text.split(";;;");
                        checkboxes.forEach(cb => { cb.checked = checkedValues.includes(cb.value); });
                    }

                    const textField = panel.querySelector(".answer-field:not(.matching-field)");
                    if (textField) textField.value = row.answer_text;

                    const flag = panel.querySelector(".flag-input");
                    if (flag) flag.checked = row.is_flagged;
                }

                // Bind input listeners for autosave dirty tracking
                panel.querySelectorAll("input, select, textarea").forEach(input => {
                    const eventName = (input.type === "radio" || input.type === "checkbox" || input.tagName === "SELECT") ? "change" : "input";
                    input.addEventListener(eventName, () => markDirty(panel));
                });
            });
        }
        setupPanelsAndAnswers();

        // Initialize First Part
        if (sectionGroups.length) {
            switchPart(0);
        }

        // Auto-spy question focus & scroll to dynamically highlight current question pill
        panels.forEach(panel => {
            panel.addEventListener("focusin", () => {
                const pill = questionNavPills?.querySelector(`.q-pill[data-question-id="${panel.dataset.questionId}"]`);
                if (pill) highlightActivePill(pill);
            });
        });

        const activeScrollArea = isReading
            ? document.getElementById("questionsScrollArea")
            : (isListening ? document.getElementById("listeningScrollArea") : null);

        if (activeScrollArea && "IntersectionObserver" in window) {
            const qObserver = new IntersectionObserver((entries) => {
                for (const entry of entries) {
                    if (entry.isIntersecting && entry.intersectionRatio >= 0.25) {
                        const qId = entry.target.dataset.questionId;
                        const pill = questionNavPills?.querySelector(`.q-pill[data-question-id="${qId}"]`);
                        if (pill) highlightActivePill(pill);
                        break;
                    }
                }
            }, {
                root: activeScrollArea,
                threshold: 0.25,
            });
            panels.forEach(p => qObserver.observe(p));
        }
    }

    // =========================================================================
    // WRITING EXAM WORKSPACE LOGIC
    // =========================================================================
    if (isWriting) {
        const questionNav = document.getElementById("questionNav");
        const prevBtn = document.getElementById("prevQuestion");
        const nextBtn = document.getElementById("nextQuestion");
        let currentIndex = 0;

        function renderWritingNavigation() {
            if (!questionNav) return;
            questionNav.innerHTML = "";
            let completed = 0;
            panels.forEach((panel, pos) => {
                const hasAnswer = getAnswer(panel).trim().length > 0;
                if (hasAnswer) completed += 1;

                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = "q-nav-btn p-2 rounded-lg border border-slate-200 text-xs font-bold text-center cursor-pointer transition-colors";
                btn.textContent = panel.dataset.taskLabel || `Task ${pos + 1}`;
                btn.classList.toggle("bg-emerald-100", hasAnswer);
                btn.classList.toggle("border-emerald-300", hasAnswer);
                btn.classList.toggle("ring-2", pos === currentIndex);
                btn.classList.toggle("ring-indigo-500", pos === currentIndex);

                btn.addEventListener("click", () => showWritingTask(pos));
                questionNav.appendChild(btn);
            });

            const answeredCountEl = document.getElementById("answeredCount");
            if (answeredCountEl) answeredCountEl.textContent = `${completed} of ${panels.length} completed`;
        }

        function showWritingTask(pos) {
            if (pos < 0 || pos >= panels.length) return;
            panels.forEach((p, idx) => { p.hidden = idx !== pos; });
            currentIndex = pos;
            if (prevBtn) prevBtn.disabled = currentIndex === 0;
            if (nextBtn) nextBtn.disabled = currentIndex === panels.length - 1;
            renderWritingNavigation();
        }

        if (panels.length) showWritingTask(0);
        if (prevBtn) prevBtn.addEventListener("click", () => showWritingTask(currentIndex - 1));
        if (nextBtn) nextBtn.addEventListener("click", () => showWritingTask(currentIndex + 1));
    }


    // Update pills and part progress counters
    function updatePillsState() {
        let totalAnswered = 0;
        document.querySelectorAll(".part-tab-button").forEach(btn => {
            const sectionId = btn.dataset.sectionId;
            const sectionPanels = panels.filter(p => p.dataset.sectionId === sectionId);
            const ansCount = sectionPanels.filter(p => getAnswer(p).trim().length > 0).length;
            totalAnswered += ansCount;
            const countLabel = btn.querySelector(".part-count");
            if (countLabel) countLabel.textContent = `${ansCount}/${sectionPanels.length}`;
        });

        document.querySelectorAll(".q-pill").forEach(pill => {
            const panel = panels.find(p => p.dataset.questionId === pill.dataset.questionId);
            if (panel) {
                const bIdx = pill.dataset.blankIndex;
                const mIdx = pill.dataset.msIndex;
                let hasAnswer = false;
                if (bIdx !== undefined) {
                    const inputs = panel.querySelectorAll(".blank-input");
                    hasAnswer = Boolean(inputs[Number(bIdx)] && inputs[Number(bIdx)].value.trim().length > 0);
                } else if (mIdx !== undefined) {
                    const checkboxes = panel.querySelectorAll('input[type="checkbox"]:not(.flag-input):checked');
                    hasAnswer = (checkboxes.length >= Number(mIdx) + 1);
                } else {
                    hasAnswer = getAnswer(panel).trim().length > 0;
                }
                const isFlagged = Boolean(panel.querySelector(".flag-input")?.checked);
                pill.classList.toggle("answered", hasAnswer);
                pill.classList.toggle("flagged", isFlagged);
            }
        });
    }
    updatePillsState();

    // Bottom Save & Submit Buttons
    if (saveBtnFooter) {
        saveBtnFooter.addEventListener("click", async () => {
            saveBtnFooter.disabled = true;
            try {
                await saveAll();
                if (saveStatus) saveStatus.textContent = "Saved";
            } catch (e) {
                console.warn(e);
            } finally {
                saveBtnFooter.disabled = false;
            }
        });
    }

    function rearmHistoryTrap() {
        try {
            window.history.pushState({ examTrap: true, token: Date.now() }, "", window.location.href);
        } catch (e) {
            console.warn("Could not push history trap state:", e);
        }
    }

    async function submitExamSession(confirmMessage, isExit = false) {
        if (finishing) return;
        submittingNormally = true;
        if (confirmMessage) {
            const confirmed = window.confirm(confirmMessage);
            if (!confirmed) {
                submittingNormally = false;
                lastViolationAt = Date.now();
                rearmHistoryTrap();
                setTimeout(rearmHistoryTrap, 50);
                setTimeout(rearmHistoryTrap, 200);
                return;
            }
        }
        if (submitBtnFooter) submitBtnFooter.disabled = true;
        if (headerBackBtn) {
            headerBackBtn.classList.add("pointer-events-none", "opacity-50");
        }
        if (saveStatus) saveStatus.textContent = "Submitting...";

        try {
            try {
                await saveAll();
            } catch (saveErr) {
                console.warn("Pre-submit save warning (proceeding with submit):", saveErr);
            }
            finishing = true;
            if (submitForm) {
                if (isExit) {
                    let exitInput = submitForm.querySelector('input[name="exit_full_mock"]');
                    if (!exitInput) {
                        exitInput = document.createElement("input");
                        exitInput.type = "hidden";
                        exitInput.name = "exit_full_mock";
                        exitInput.value = "true";
                        submitForm.appendChild(exitInput);
                    }
                }
                HTMLFormElement.prototype.submit.call(submitForm);
            } else if (app?.dataset?.endedUrl || app?.dataset?.resultUrl) {
                window.location.replace(app.dataset.endedUrl || app.dataset.resultUrl);
            }
        } catch (error) {
            console.error("Submission save error:", error);
            alert("Some answers could not be saved. Please check your internet connection and try again.");
            if (submitBtnFooter) submitBtnFooter.disabled = false;
            if (headerBackBtn) {
                headerBackBtn.classList.remove("pointer-events-none", "opacity-50");
            }
            if (saveStatus) saveStatus.textContent = "Error saving";
            submittingNormally = false;
            rearmHistoryTrap();
        }
    }

    const isFullMock = app?.dataset?.isFullMock === "true";
    const currentModuleType = app?.dataset?.moduleType || (isReading ? "reading" : isListening ? "listening" : "writing");

    if (submitBtnFooter) {
        submitBtnFooter.addEventListener("click", () => {
            let msg = "Are you sure you want to submit your examination? You cannot modify answers after submitting.";
            if (isFullMock) {
                if (currentModuleType === "reading") {
                    msg = "Are you sure you want to submit Reading and proceed to the Listening module? You cannot change Reading answers after submitting.";
                } else if (currentModuleType === "listening") {
                    msg = "Are you sure you want to submit Listening and proceed to the Writing module? You cannot change Listening answers after submitting.";
                } else if (currentModuleType === "writing") {
                    msg = "Are you sure you want to finalize and submit all modules of your IELTS Examination?";
                }
            }
            void submitExamSession(msg, false);
        });
    }

    // Top Header Back button triggers exam submission
    if (headerBackBtn) {
        headerBackBtn.addEventListener("click", (e) => {
            e.preventDefault();
            e.stopPropagation();
            const msg = isFullMock
                ? "Going back will exit your All-Module exam and submit your work so far. Are you sure you want to exit and submit?"
                : "Going back will submit your examination. Are you sure you want to exit and submit?";
            void submitExamSession(msg, true);
        });
    }

    // Submit form handler
    if (submitForm) {
        submitForm.addEventListener("submit", (e) => {
            e.preventDefault();
            let msg = "Are you sure you want to submit your examination? You cannot modify answers after submitting.";
            if (isFullMock) {
                if (currentModuleType === "reading") {
                    msg = "Are you sure you want to submit Reading and proceed to the Listening module? You cannot change Reading answers after submitting.";
                } else if (currentModuleType === "listening") {
                    msg = "Are you sure you want to submit Listening and proceed to the Writing module? You cannot change Listening answers after submitting.";
                } else if (currentModuleType === "writing") {
                    msg = "Are you sure you want to finalize and submit all modules of your IELTS Examination?";
                }
            }
            void submitExamSession(msg, false);
        });
    }

    // Browser back button interception (popstate)
    let popstateHandling = false;
    try {
        rearmHistoryTrap();
        window.addEventListener("popstate", () => {
            if (finishing) return;
            rearmHistoryTrap();
            if (popstateHandling) return;
            popstateHandling = true;

            const msg = isFullMock
                ? "Going back will exit your All-Module exam and submit your work so far. Are you sure you want to exit and submit?"
                : "Going back will submit your examination. Are you sure you want to exit and submit?";

            setTimeout(async () => {
                try {
                    await submitExamSession(msg, true);
                } finally {
                    popstateHandling = false;
                    rearmHistoryTrap();
                }
            }, 30);
        });
    } catch (e) {
        console.warn("Could not register popstate listener:", e);
    }

    // Timers & Autosaves
    setInterval(() => { if (!finishing) void saveAll().catch(console.warn); }, 15000);
    setInterval(paintTimer, 1000);
    setInterval(syncTimer, 10000);
    paintTimer();

    // =========================================================================
    // EXAM INTEGRITY VIOLATION MONITORING
    // =========================================================================
    async function reportViolation(reason) {
        if (finishing || submittingNormally || violationPending) return;
        const now = Date.now();
        if (now - lastViolationAt < 1000) return;
        lastViolationAt = now;
        violationPending = true;

        try {
            const response = await fetch(app.dataset.violationUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": document.querySelector('[name="csrfmiddlewaretoken"]')?.value || "",
                },
                body: JSON.stringify({ reason }),
                keepalive: true,
            });
            const data = await response.json().catch(() => ({}));
            if (response.status === 409 || data.status === "auto_submitted" || data.auto_submitted) {
                finishing = true;
                const dest = data.redirect_url || app.dataset.endedUrl || app.dataset.resultUrl;
                window.location.replace(dest);
                return;
            }
            if (data.warning && violationModal) {
                warningOpen = true;
                const titleEl = document.getElementById("violationTitle");
                if (titleEl && data.warning_title) {
                    titleEl.textContent = data.warning_title;
                }
                if (violationMessage && data.warning_message) {
                    violationMessage.textContent = data.warning_message;
                }
                violationModal.hidden = false;
                if (!document.hidden && acknowledgeViolation) {
                    acknowledgeViolation.focus();
                }
            }
        } catch (error) {
            console.warn("Could not record focus loss:", error);
        } finally {
            violationPending = false;
        }
    }

    if (acknowledgeViolation && violationModal) {
        acknowledgeViolation.addEventListener("click", () => {
            violationModal.hidden = true;
            warningOpen = false;
            lastViolationAt = 0;
        });
    }

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            void reportViolation("tab_hidden");
        } else {
            if (warningOpen && acknowledgeViolation) acknowledgeViolation.focus();
            void syncTimer();
        }
    });

    window.addEventListener("blur", () => {
        setTimeout(() => {
            if (!document.hidden && !warningOpen && !document.hasFocus()) {
                void reportViolation("window_blur");
            }
        }, 500);
    });

    // =========================================================================
    // LISTENING AUDIO PLAYER LOGIC (Continuous Master Audio OR Part-by-Part Audio)
    // =========================================================================
    if (isListening) {
        const audio = document.getElementById("listeningAudio");
        const start = document.getElementById("startListening");
        const status = document.getElementById("listeningStatus");
        const pulseDot = document.getElementById("listeningPulseDot");
        const parts = Array.from(document.querySelectorAll(".listening-part"));
        const progressRow = document.getElementById("listeningProgressRow");
        const progressTrack = document.getElementById("listeningProgressTrack");
        const progressBar = document.getElementById("listeningProgressBar");
        const timeLabel = document.getElementById("listeningTimeLabel");
        const partBadge = document.getElementById("listeningPartBadge");
        const volumeBtn = document.getElementById("listeningVolumeBtn");
        const volumeSlider = document.getElementById("listeningVolumeSlider");
        const volumeIcon = document.getElementById("listeningVolumeIcon");
        const volumeLabel = document.getElementById("listeningVolumeLabel");
        const audioWave = document.getElementById("listeningAudioWave");
        const staticIcon = document.getElementById("listeningStaticIcon");

        // Mode detection:
        // 1. Continuous master audio: Admin uploaded one master audio covering the entire module.
        // 2. Individual section audio: Admin uploaded audio for each section/part.
        let moduleAudioUrl = audio ? (audio.dataset.moduleAudioUrl || "").trim() : "";
        let isSingleAudioMode = Boolean(moduleAudioUrl);
        const hasSectionAudios = parts.length > 0 && parts.some(p => Boolean(p.dataset.audioUrl));

        let currentPart = 0;
        let started = false;
        let advancing = false;

        const audioStateKey = `ielts_listening_audio_${app.dataset.attemptId || "curr"}`;

        function isPlaybackUnavailable() {
            if (isSingleAudioMode) {
                return !moduleAudioUrl && !hasSectionAudios;
            }
            return !hasSectionAudios;
        }

        let unavailable = isPlaybackUnavailable();
        if (unavailable && start) {
            start.disabled = true;
            if (status) status.textContent = "Audio not configured for this Listening module.";
        }

        function setWaveAnimation(active) {
            if (audioWave) {
                audioWave.classList.toggle("hidden", !active);
                audioWave.classList.toggle("playing", active);
            }
            if (staticIcon) {
                staticIcon.classList.toggle("hidden", active);
            }
        }

        function setPulse(active, isAmber = false) {
            if (!pulseDot) return;
            if (!active) {
                pulseDot.className = "w-2 h-2 rounded-full bg-slate-300 dark:bg-zinc-600 transition-colors";
            } else if (isAmber) {
                pulseDot.className = "w-2 h-2 rounded-full bg-amber-400 animate-pulse pulse-amber-glow";
            } else {
                pulseDot.className = "w-2 h-2 rounded-full bg-emerald-500 animate-pulse pulse-emerald-glow";
            }
        }

        function updatePartBadge(partIndex) {
            if (!partBadge) return;
            if (isSingleAudioMode) {
                partBadge.textContent = "Full Audio";
            } else {
                partBadge.textContent = `Part ${partIndex + 1}`;
            }
        }

        let playRequestedAt = 0;
        let playTransitionTimer = null;

        function schedulePlayingTransition(callback) {
            if (playTransitionTimer) {
                clearTimeout(playTransitionTimer);
                playTransitionTimer = null;
            }
            const minStartDisplayMs = 500;
            const elapsed = Date.now() - playRequestedAt;
            const remaining = Math.max(0, minStartDisplayMs - elapsed);
            if (remaining > 0) {
                playTransitionTimer = setTimeout(() => {
                    playTransitionTimer = null;
                    callback();
                }, remaining);
            } else {
                callback();
            }
        }

        function cancelPlayingTransition() {
            if (playTransitionTimer) {
                clearTimeout(playTransitionTimer);
                playTransitionTimer = null;
            }
        }

        function setButtonState(state, customLabel = null) {
            if (!start) return;
            start.hidden = false;
            start.className = `listening-audio-btn state-${state}`;

            if (state === "ready") {
                start.disabled = false;
                start.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg> <span>${customLabel || "Start listening audio"}</span>`;
            } else if (state === "starting") {
                start.disabled = true;
                start.innerHTML = `<span class="live-spin-icon"></span> <span>${customLabel || "Audio starting..."}</span>`;
            } else if (state === "playing") {
                start.disabled = true;
                start.innerHTML = `<span class="live-pulse-dot"></span><span>${customLabel || "Audio playing..."}</span>`;
            } else if (state === "paused") {
                start.disabled = true;
                start.innerHTML = `<span>${customLabel || "Audio in progress (continuous)"}</span>`;
            } else if (state === "complete") {
                start.disabled = true;
                start.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> <span>Listening audio complete</span>`;
            } else if (state === "error") {
                start.disabled = false;
                start.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg> <span>Retry listening audio</span>`;
            }
        }

        function formatTime(sec) {
            sec = Math.max(0, Math.floor(sec || 0));
            const m = Math.floor(sec / 60);
            const s = Math.floor(sec % 60);
            return `${m}:${s < 10 ? "0" : ""}${s}`;
        }

        function updateProgress() {
            if (!audio) return;
            const cur = audio.currentTime || 0;
            const dur = audio.duration || 0;
            if (progressRow) {
                progressRow.classList.remove("opacity-60");
                progressRow.classList.add("opacity-100");
            }
            if (timeLabel) {
                timeLabel.textContent = `${formatTime(cur)} / ${dur > 0 && isFinite(dur) ? formatTime(dur) : "0:00"}`;
            }
            if (progressBar && dur > 0 && isFinite(dur)) {
                const pct = Math.min(100, Math.max(0, (cur / dur) * 100));
                progressBar.style.width = `${pct}%`;
            }
        }

        function applySeek(targetTime) {
            if (targetTime <= 0 || !audio) return;
            if (audio.readyState >= 1) {
                try {
                    audio.currentTime = targetTime;
                    updateProgress();
                } catch (e) {
                    console.warn("Audio seek error:", e);
                }
            } else {
                const onMeta = () => {
                    try {
                        audio.currentTime = targetTime;
                        updateProgress();
                    } catch (e) {
                        console.warn("Audio seek error on metadata:", e);
                    }
                    audio.removeEventListener("loadedmetadata", onMeta);
                };
                audio.addEventListener("loadedmetadata", onMeta, { once: true });
            }
        }

        // Click on progress track to seek
        if (progressTrack) {
            progressTrack.addEventListener("click", (e) => {
                if (!audio || !audio.duration || isNaN(audio.duration)) return;
                const rect = progressTrack.getBoundingClientRect();
                const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                audio.currentTime = pos * audio.duration;
                updateProgress();
            });
        }

        // Volume control management
        let lastVolume = 1;
        try {
            const savedVol = localStorage.getItem("ielts_listening_volume");
            if (savedVol !== null && !isNaN(parseFloat(savedVol))) {
                lastVolume = parseFloat(savedVol);
            }
        } catch (e) {}

        function setVolume(val) {
            if (!audio) return;
            val = Math.max(0, Math.min(1, val));
            audio.volume = val;
            if (volumeSlider) volumeSlider.value = val;
            if (volumeLabel) volumeLabel.textContent = `${Math.round(val * 100)}%`;
            try { localStorage.setItem("ielts_listening_volume", String(val)); } catch (e) {}

            if (volumeIcon) {
                if (val === 0) {
                    volumeIcon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" d="M17.25 9.75L21.75 14.25M21.75 9.75L17.25 14.25M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.757 3.63 8.25 4.51 8.25H6.75z" />`;
                } else if (val < 0.5) {
                    volumeIcon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" d="M15.536 8.464a5 5 0 010 7.072M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.757 3.63 8.25 4.51 8.25H6.75z" />`;
                } else {
                    volumeIcon.innerHTML = `<path stroke-linecap="round" stroke-linejoin="round" d="M19.114 5.636a9 9 0 010 12.728M16.463 8.288a5.25 5.25 0 010 7.424M6.75 8.25l4.72-4.72a.75.75 0 011.28.53v15.88a.75.75 0 01-1.28.53l-4.72-4.72H4.51c-.88 0-1.704-.507-1.938-1.354A9.01 9.01 0 012.25 12c0-.83.112-1.633.322-2.396C2.806 8.757 3.63 8.25 4.51 8.25H6.75z" />`;
                }
            }
        }

        setVolume(lastVolume);

        if (volumeSlider) {
            volumeSlider.addEventListener("input", (e) => {
                setVolume(parseFloat(e.target.value));
            });
        }

        if (volumeBtn) {
            let unmutedVal = 0.8;
            volumeBtn.addEventListener("click", () => {
                if (!audio) return;
                if (audio.volume > 0) {
                    unmutedVal = audio.volume;
                    setVolume(0);
                } else {
                    setVolume(unmutedVal || 0.8);
                }
            });
        }

        // Mode A: Master Continuous Audio (covers all sections/questions)
        async function playModuleAudio(seekTime = 0) {
            if (finishing || !audio || !moduleAudioUrl) return;
            try {
                updatePartBadge(0);
                if (audio.getAttribute("src") !== moduleAudioUrl) {
                    audio.src = moduleAudioUrl;
                }
                applySeek(seekTime);
                const playPromise = audio.play();
                if (playPromise !== undefined) {
                    await playPromise;
                }
                started = true;
            } catch (err) {
                console.warn("Continuous audio play failed:", err);
                cancelPlayingTransition();
                setPulse(false);
                setWaveAnimation(false);
                if (hasSectionAudios) {
                    console.info("Continuous audio failed, falling back to section audio mode");
                    isSingleAudioMode = false;
                    moduleAudioUrl = "";
                    void playSectionAudio(0, 0);
                    return;
                }
                setButtonState("error", "Audio unavailable");
                if (status) status.textContent = "Audio playback failed. Click Retry listening audio to begin.";
            }
        }

        // Mode B: Individual Section Audio (plays part-by-part sequentially)
        async function playSectionAudio(position, seekTime = 0) {
            if (finishing || !audio || position >= parts.length) {
                cancelPlayingTransition();
                if (status) status.textContent = "Listening audio complete. You may review your answers before submitting.";
                setPulse(false);
                setWaveAnimation(false);
                setButtonState("complete");
                try {
                    sessionStorage.setItem(audioStateKey, JSON.stringify({
                        mode: "section",
                        started: true,
                        completed: true,
                        currentPart: position,
                        currentTime: 0,
                    }));
                } catch (e) {}
                return;
            }
            const part = parts[position];
            currentPart = position;
            updatePartBadge(position);
            const partUrl = part.dataset.audioUrl || "";
            if (!partUrl) {
                console.warn(`Part ${position + 1} has no audio URL`);
                cancelPlayingTransition();
                if (status) status.textContent = `Part ${position + 1} audio is unavailable.`;
                setButtonState("error");
                setWaveAnimation(false);
                return;
            }
            try {
                if (audio.getAttribute("src") !== partUrl) {
                    audio.src = partUrl;
                }
                applySeek(seekTime);
                const playPromise = audio.play();
                if (playPromise !== undefined) {
                    await playPromise;
                }
                started = true;
            } catch (err) {
                console.warn(`Audio playback for Part ${position + 1} error:`, err);
                cancelPlayingTransition();
                setPulse(false);
                setWaveAnimation(false);
                setButtonState("error", `Retry Part ${position + 1} audio`);
                if (status) status.textContent = `Part ${position + 1} audio error. Click Retry to try again.`;
            }
        }

        // Unified Play Trigger with guaranteed user feedback
        function startOrResumePlayback(resumePart = 0, resumeTime = 0) {
            started = true;
            playRequestedAt = Date.now();
            setButtonState("starting", "Audio starting...");
            setPulse(true, true);
            updatePartBadge(resumePart);
            if (status) {
                if (isSingleAudioMode) {
                    status.textContent = "Audio starting... Preparing continuous listening audio...";
                } else {
                    const partTitle = parts[resumePart]?.dataset.title || `Part ${resumePart + 1}`;
                    status.textContent = `Audio starting... Buffering ${partTitle}...`;
                }
            }

            // Execute immediately within the user gesture call stack
            if (isSingleAudioMode) {
                void playModuleAudio(resumeTime);
            } else {
                void playSectionAudio(resumePart, resumeTime);
            }
        }

        // External Part Switch Listener from bottom footer
        window.onListeningPartSwitched = function(partIndex) {
            if (!isListening) return;
            updatePartBadge(partIndex);
            if (!started || (audio && audio.paused && audio.currentTime === 0)) {
                currentPart = partIndex;
                if (parts[partIndex]) {
                    const partUrl = parts[partIndex].dataset.audioUrl || "";
                    if (partUrl && audio && audio.getAttribute("src") !== partUrl) {
                        audio.src = partUrl;
                    }
                    if (status) {
                        status.textContent = `Audio ready. Click "Start listening audio" to begin Part ${partIndex + 1}.`;
                    }
                    setButtonState("ready", `Start Part ${partIndex + 1} audio`);
                }
            } else if (audio && !audio.paused && !isSingleAudioMode) {
                if (currentPart !== partIndex) {
                    if (status) {
                        status.textContent = `Playing Part ${currentPart + 1} audio (Viewing Part ${partIndex + 1} questions)`;
                    }
                } else {
                    if (status) {
                        status.textContent = `Playing Part ${currentPart + 1} of ${parts.length}: ${parts[currentPart]?.dataset.title || ""}`;
                    }
                }
            }
        };

        // Restore playback state on page load/reload
        try {
            const savedStr = sessionStorage.getItem(audioStateKey);
            if (savedStr) {
                const saved = JSON.parse(savedStr);
                if (saved.completed) {
                    if (status) status.textContent = "Listening audio complete. You may review your answers before submitting.";
                    setButtonState("complete");
                    setPulse(false);
                    setWaveAnimation(false);
                } else if (saved.started && !unavailable) {
                    setButtonState("paused", "Audio in progress");
                    if (status) status.textContent = "Listening examination audio is continuous.";
                    updatePartBadge(saved.currentPart || 0);
                }
            } else {
                // Initial prompt when session starts fresh
                if (!unavailable && status) {
                    if (isSingleAudioMode) {
                        status.textContent = "Continuous examination audio (covers all parts). Click \"Start listening audio\" to begin.";
                    } else {
                        status.textContent = "Individual section audio. Click \"Start listening audio\" to begin Part 1.";
                    }
                    setButtonState("ready", "Start listening audio");
                    updatePartBadge(0);
                }
            }
        } catch (e) {
            console.warn("Audio restore error:", e);
        }

        if (start) {
            start.addEventListener("click", () => {
                if (isPlaybackUnavailable()) return;

                // 1. In listening examination, audio plays continuously and cannot be paused
                if (audio && !audio.paused && started) {
                    return;
                }

                // 2. Resume button must NOT work in listening module
                if (audio && audio.paused && started) {
                    console.warn("Resume is disabled in listening module.");
                    return;
                }

                // 3. Audio completed: replay is disabled in listening examination
                try {
                    const savedStr = sessionStorage.getItem(audioStateKey);
                    if (savedStr) {
                        const saved = JSON.parse(savedStr);
                        if (saved.completed) {
                            return;
                        }
                    }
                } catch (e) {}

                // 4. Fresh start
                const targetPart = isSingleAudioMode ? 0 : (activeSectionIndex || 0);
                startOrResumePlayback(targetPart, 0);
            });
        }

        if (audio) {
            // Buffer metadata in advance
            try { audio.load(); } catch (e) {}

            audio.addEventListener("playing", () => {
                started = true;
                schedulePlayingTransition(() => {
                    setPulse(true, false);
                    setWaveAnimation(true);
                    setButtonState("playing");
                    updatePartBadge(currentPart);
                    updateProgress();
                    if (status) {
                        if (isSingleAudioMode) {
                            status.textContent = "Playing continuous listening audio (covers Parts 1–4)";
                        } else {
                            const part = parts[currentPart];
                            const viewingPart = activeSectionIndex;
                            if (viewingPart !== currentPart) {
                                status.textContent = `Playing Part ${currentPart + 1} audio (Viewing Part ${viewingPart + 1} questions)`;
                            } else {
                                status.textContent = `Playing Part ${currentPart + 1} of ${parts.length}: ${part ? part.dataset.title : ""}`;
                            }
                        }
                    }
                });
            });

            audio.addEventListener("waiting", () => {
                setButtonState("starting", "Buffering audio...");
                setPulse(true, true);
                if (status) status.textContent = "Buffering listening audio stream...";
            });

            audio.addEventListener("pause", () => {
                cancelPlayingTransition();
                if (!advancing && !finishing && started && !audio.ended) {
                    setPulse(false);
                    setWaveAnimation(false);
                    setButtonState("paused", "Audio in progress");
                    if (status) status.textContent = "Listening examination audio cannot be paused or resumed.";
                }
            });

            audio.addEventListener("error", (e) => {
                console.warn("Audio element playback error:", audio.error, e);
                cancelPlayingTransition();
                setPulse(false);
                setWaveAnimation(false);
                if (isSingleAudioMode && hasSectionAudios) {
                    console.info("Continuous audio media error, falling back to section audio mode");
                    isSingleAudioMode = false;
                    moduleAudioUrl = "";
                    void playSectionAudio(0, 0);
                    return;
                }
                if (status) status.textContent = "Audio playback error. Click Retry to try again.";
                setButtonState("error");
            });

            audio.addEventListener("loadedmetadata", () => {
                updateProgress();
            });

            audio.addEventListener("durationchange", () => {
                updateProgress();
            });

            audio.addEventListener("timeupdate", () => {
                if (!started) return;
                updateProgress();
                try {
                    if (isSingleAudioMode) {
                        sessionStorage.setItem(audioStateKey, JSON.stringify({
                            mode: "module",
                            started: true,
                            completed: false,
                            currentTime: audio.currentTime,
                        }));
                    } else {
                        sessionStorage.setItem(audioStateKey, JSON.stringify({
                            mode: "section",
                            started: true,
                            completed: false,
                            currentPart: currentPart,
                            currentTime: audio.currentTime,
                        }));
                    }
                } catch (e) {}
            });

            audio.addEventListener("ended", async () => {
                if (advancing || finishing) return;
                advancing = true;
                setWaveAnimation(false);
                try {
                    if (isSingleAudioMode) {
                        if (status) status.textContent = "Listening audio complete. You may review your answers before submitting.";
                        setPulse(false);
                        setButtonState("complete");
                        try {
                            sessionStorage.setItem(audioStateKey, JSON.stringify({
                                mode: "module",
                                started: true,
                                completed: true,
                                currentTime: audio.currentTime || 0,
                            }));
                        } catch (e) {}
                    } else {
                        const nextPart = currentPart + 1;
                        if (nextPart < parts.length) {
                            playRequestedAt = Date.now();
                            setButtonState("starting", `Starting Part ${nextPart + 1}...`);
                            setPulse(true, true);
                            updatePartBadge(nextPart);
                            if (status) status.textContent = `Part ${currentPart + 1} finished. Audio starting for Part ${nextPart + 1}...`;
                            if (typeof switchPart === "function") {
                                switchPart(nextPart);
                            }
                            await playSectionAudio(nextPart);
                        } else {
                            if (status) status.textContent = "Listening audio complete. You may review your answers before submitting.";
                            setPulse(false);
                            setButtonState("complete");
                            try {
                                sessionStorage.setItem(audioStateKey, JSON.stringify({
                                    mode: "section",
                                    started: true,
                                    completed: true,
                                    currentPart: currentPart,
                                    currentTime: 0,
                                }));
                            } catch (e) {}
                        }
                    }
                } finally {
                    advancing = false;
                }
            });

            audio.controls = false;
        }
    }

    // Prevent accidental unload/reload while exam is in progress
    window.addEventListener("beforeunload", (e) => {
        if (!finishing && !submittingNormally) {
            e.preventDefault();
            e.returnValue = "";
        }
    });
});
