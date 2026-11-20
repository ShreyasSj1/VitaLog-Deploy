// AI Fitness Coach Chatbot Controller
(function() {
    const chatToggle = document.getElementById('chatToggle');
    const chatClose = document.getElementById('chatClose');
    const chatPopup = document.getElementById('chatPopup');
    const chatInput = document.getElementById('chatInput');
    const chatSend = document.getElementById('chatSend');
    const chatMessages = document.getElementById('chatMessages');
    const typingIndicator = document.getElementById('typingIndicator');
    const chatTooltip = document.getElementById('chatTooltip');
    const tooltipClose = document.getElementById('tooltipClose');
    const chatbotContainer = document.querySelector('.chatbot-container');
    const csrfToken = chatbotContainer?.getAttribute('data-csrf-token')
        || document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
        || '';

    if (!chatToggle) return;

    // Show tooltip after 2.5s delay
    let tooltipTimeout = setTimeout(() => {
        if (chatTooltip && !chatPopup.classList.contains('active')) {
            chatTooltip.classList.add('show');
        }
    }, 2500);

    if (tooltipClose) {
        tooltipClose.addEventListener('click', (e) => {
            e.stopPropagation();
            chatTooltip.classList.remove('show');
            clearTimeout(tooltipTimeout);
        });
    }

    chatToggle.addEventListener('click', () => {
        chatPopup.classList.toggle('active');
        if (chatPopup.classList.contains('active')) {
            if (window.innerWidth > 768 && chatInput) {
                chatInput.focus();
            }
            if (chatTooltip) chatTooltip.classList.remove('show');
            clearTimeout(tooltipTimeout);
            loadChatHistory().then(() => {
                checkActiveDraft();
                setTimeout(scrollMessagesToBottom, 100);
            });
        }
    });

    if (chatClose) {
        chatClose.addEventListener('click', () => {
            chatPopup.classList.remove('active');
            chatPopup.style.height = '';
        });
    }

    // Handle suggestion chip clicks
    const suggestionChips = document.querySelectorAll('.suggestion-chip');
    suggestionChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.getAttribute('data-query');
            if (query && chatInput) {
                chatInput.value = query;
                sendMessage();
            }
        });
    });

    function scrollMessagesToBottom() {
        if (chatMessages) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    // Dynamic sizing helper to keep chats and inputs visible above mobile virtual keyboard
    if (window.visualViewport && chatPopup && chatInput) {
        const handleViewportChange = () => {
            if (window.innerWidth > 768) {
                chatPopup.style.height = '';
                return;
            }
            if (chatPopup.classList.contains('active')) {
                const height = window.visualViewport.height;
                chatPopup.style.height = `${height * 0.75}px`;
                scrollMessagesToBottom();
            } else {
                chatPopup.style.height = '';
            }
        };

        window.visualViewport.addEventListener('resize', handleViewportChange);
        window.visualViewport.addEventListener('scroll', handleViewportChange);

        chatInput.addEventListener('focus', () => {
            setTimeout(handleViewportChange, 150);
        });

        chatInput.addEventListener('blur', () => {
            setTimeout(() => {
                if (window.innerWidth <= 768) {
                    if (!chatPopup.classList.contains('active')) {
                        chatPopup.style.height = '';
                    }
                }
            }, 150);
        });
    }

    let historyLoaded = false;

    async function loadChatHistory() {
        if (historyLoaded) return;
        try {
            const response = await fetch('/chat/history');
            if (response.status === 401) return;
            const data = await response.json();
            
            if (data.messages && data.messages.length > 0 && chatMessages) {
                chatMessages.innerHTML = '';
                data.messages.forEach(msg => {
                    addMessage(msg.content, msg.role === 'assistant' ? 'ai' : 'user');
                });
            }
            historyLoaded = true;
        } catch (error) {
            console.error('Error loading chat history:', error);
        }
    }

    function escapeHtml(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function addMessage(text, sender) {
        if (!chatMessages) return;
        const msgDiv = document.createElement('div');
        msgDiv.classList.add('message', sender);
        msgDiv.innerText = text;
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function renderDraftCard(draft) {
        if (!draft || !draft.data || !chatMessages) return;

        // Remove any prior rendered card with this draft_id
        const existing = document.getElementById(`draft-card-${draft.draft_id}`);
        if (existing) {
            existing.remove();
        }

        const card = document.createElement('div');
        card.id = `draft-card-${draft.draft_id}`;
        card.className = 'chat-draft-card';

        const isFood = draft.log_type === 'food';
        const data = draft.data;

        let html = `
            <div class="chat-draft-header">
                <span class="chat-draft-title">
                    ${isFood ? '🥗 Meal Draft' : '🏋️ Workout Draft'}
                    <span class="text-muted" style="font-size:0.8rem; font-weight:normal;">(${escapeHtml(data.date || 'Today')})</span>
                </span>
                <span class="chat-draft-badge-type ${draft.log_type}">${isFood ? escapeHtml(data.meal || 'Food') : 'Workout'}</span>
            </div>
        `;

        if (isFood && data.items && data.items.length > 0) {
            html += `
                <table class="chat-draft-table">
                    <thead>
                        <tr>
                            <th>Item</th>
                            <th>Qty</th>
                            <th>Cals</th>
                            <th>Macros</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            data.items.forEach(it => {
                const badgeClass = it.provenance === 'catalog' ? 'badge-catalog' : (it.provenance === 'ai_estimate' || it.is_estimate ? 'badge-estimate' : 'badge-custom');
                const badgeLabel = it.provenance === 'catalog' ? 'Catalog' : (it.provenance === 'ai_estimate' || it.is_estimate ? 'AI Est' : 'Custom');
                html += `
                    <tr>
                        <td>
                            <strong>${escapeHtml(it.food)}</strong>
                            <span class="badge-draft ${badgeClass}">${badgeLabel}</span>
                        </td>
                        <td>${it.qty}</td>
                        <td>${Math.round(it.calories || 0)}</td>
                        <td class="text-muted" style="font-size:0.75rem;">${Math.round(it.protein || 0)}P · ${Math.round(it.fat || 0)}F</td>
                    </tr>
                `;
            });
            html += `</tbody></table>`;

            if (data.totals) {
                html += `
                    <div class="chat-draft-totals">
                        <span>Total Nutrition:</span>
                        <span><strong>${Math.round(data.totals.calories || 0)} kcal</strong> (${Math.round(data.totals.protein || 0)}g P · ${Math.round(data.totals.fat || 0)}g F · ${Math.round(data.totals.sugar || 0)}g S)</span>
                    </div>
                `;
            }
        } else if (!isFood && data.exercises && data.exercises.length > 0) {
            html += `
                <table class="chat-draft-table">
                    <thead>
                        <tr>
                            <th>Exercise</th>
                            <th>Work</th>
                            <th>Est. Burn</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            data.exercises.forEach(ex => {
                let workDesc = '';
                if (ex.is_cardio) {
                    workDesc = `${ex.duration}m @ ${ex.speed}km/h`;
                    if (ex.incline > 0) workDesc += ` (inc ${ex.incline})`;
                } else {
                    const avgReps = ex.sets > 0 ? Math.round(ex.reps / ex.sets) : ex.reps;
                    workDesc = `${ex.sets} sets × ${avgReps} reps @ ${ex.weight}kg`;
                }
                html += `
                    <tr>
                        <td>
                            <strong>${escapeHtml(ex.exercise)}</strong>
                            <div class="text-muted" style="font-size:0.75rem;">${escapeHtml(ex.muscle || '')}</div>
                        </td>
                        <td>${workDesc}</td>
                        <td>${Math.round(ex.calories || 0)} kcal</td>
                    </tr>
                `;
            });
            html += `</tbody></table>`;

            if (data.total_estimated_calories != null) {
                html += `
                    <div class="chat-draft-totals">
                        <span>Total Estimated Burn:</span>
                        <span><strong>${Math.round(data.total_estimated_calories)} kcal</strong></span>
                    </div>
                `;
            }
        }

        // Action buttons or Status
        if (draft.state === 'confirmed') {
            html += `<div class="chat-draft-status-banner saved">✅ Saved to your logs!</div>`;
        } else if (draft.state === 'cancelled') {
            html += `<div class="chat-draft-status-banner cancelled">❌ Draft cancelled</div>`;
        } else if (draft.state === 'expired') {
            html += `<div class="chat-draft-status-banner cancelled">⏳ Draft expired</div>`;
        } else if (draft.state === 'awaiting_confirmation') {
            html += `
                <div class="chat-draft-actions" id="actions-${draft.draft_id}">
                    <button type="button" class="btn-draft-confirm" id="confirm-btn-${draft.draft_id}">
                        ✓ Confirm & Log ${isFood ? 'Meal' : 'Workout'}
                    </button>
                    <button type="button" class="btn-draft-cancel" id="cancel-btn-${draft.draft_id}">
                        Cancel
                    </button>
                </div>
            `;
        } else if (draft.state === 'collecting') {
            const missingText = draft.missing_fields && draft.missing_fields.length > 0 
                ? draft.missing_fields.join(', ') 
                : 'portion sizes';
            html += `
                <div class="chat-draft-missing-banner">
                    ⚠️ Missing: ${escapeHtml(missingText)} - reply in chat to clarify!
                </div>
                <div class="chat-draft-actions" id="actions-${draft.draft_id}">
                    <button type="button" class="btn-draft-confirm" id="confirm-btn-${draft.draft_id}" disabled title="Please clarify missing details in chat">
                        ✓ Confirm & Log ${isFood ? 'Meal' : 'Workout'}
                    </button>
                    <button type="button" class="btn-draft-cancel" id="cancel-btn-${draft.draft_id}">
                        Cancel
                    </button>
                </div>
            `;
        }

        card.innerHTML = html;
        chatMessages.appendChild(card);
        chatMessages.scrollTop = chatMessages.scrollHeight;

        // Attach event listeners for active draft cards
        if (draft.state === 'awaiting_confirmation' || draft.state === 'collecting') {
            const confirmBtn = document.getElementById(`confirm-btn-${draft.draft_id}`);
            const cancelBtn = document.getElementById(`cancel-btn-${draft.draft_id}`);

            if (confirmBtn && !confirmBtn.disabled) {
                confirmBtn.addEventListener('click', async () => {
                    confirmBtn.disabled = true;
                    confirmBtn.innerText = 'Saving...';
                    try {
                        const res = await fetch('/chat/draft/confirm', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-Token': csrfToken
                            },
                            body: JSON.stringify({ draft_id: draft.draft_id })
                        });
                        const resData = await res.json();
                        if (resData.success) {
                            const actionsDiv = document.getElementById(`actions-${draft.draft_id}`);
                            if (actionsDiv) {
                                actionsDiv.innerHTML = `<div class="chat-draft-status-banner saved">✅ Saved to your logs!</div>`;
                            }
                            const missingBanner = card.querySelector('.chat-draft-missing-banner');
                            if (missingBanner) {
                                missingBanner.remove();
                            }
                            if (resData.reply) {
                                addMessage(resData.reply, 'ai');
                            }
                            const path = window.location.pathname;
                            if (path.includes('/food') || path.includes('/gym') || path === '/') {
                                setTimeout(() => window.location.reload(), 1200);
                            }
                        } else {
                            confirmBtn.disabled = false;
                            confirmBtn.innerText = `✓ Confirm & Log ${isFood ? 'Meal' : 'Workout'}`;
                            alert(resData.error || 'Failed to save draft.');
                        }
                    } catch (err) {
                        confirmBtn.disabled = false;
                        confirmBtn.innerText = `✓ Confirm & Log ${isFood ? 'Meal' : 'Workout'}`;
                        console.error('Error confirming draft:', err);
                    }
                });
            }

            if (cancelBtn) {
                cancelBtn.addEventListener('click', async () => {
                    cancelBtn.disabled = true;
                    try {
                        const res = await fetch('/chat/draft/cancel', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRF-Token': csrfToken
                            },
                            body: JSON.stringify({ draft_id: draft.draft_id })
                        });
                        const resData = await res.json();
                        const actionsDiv = document.getElementById(`actions-${draft.draft_id}`);
                        if (actionsDiv) {
                            actionsDiv.innerHTML = `<div class="chat-draft-status-banner cancelled">❌ Draft cancelled</div>`;
                        }
                        const missingBanner = card.querySelector('.chat-draft-missing-banner');
                        if (missingBanner) {
                            missingBanner.remove();
                        }
                        if (resData.reply) {
                            addMessage(resData.reply, 'ai');
                        }
                    } catch (err) {
                        cancelBtn.disabled = false;
                        console.error('Error cancelling draft:', err);
                    }
                });
            }
        }
    }

    async function checkActiveDraft() {
        try {
            const res = await fetch('/chat/draft/active');
            if (res.status === 200) {
                const data = await res.json();
                if (data && data.active_draft) {
                    renderDraftCard(data.active_draft);
                }
            }
        } catch (err) {
            console.error('Error checking active draft:', err);
        }
    }

    window.openChatWithPrompt = function(promptText) {
        if (!chatPopup.classList.contains('active')) {
            chatPopup.classList.add('active');
        }
        if (chatInput) {
            chatInput.value = promptText || '';
            chatInput.focus();
        }
        loadChatHistory().then(() => {
            checkActiveDraft();
            setTimeout(scrollMessagesToBottom, 100);
        });
    };

    async function sendMessage() {
        if (!chatInput) return;
        const message = chatInput.value.trim();
        if (!message) return;

        addMessage(message, 'user');
        chatInput.value = '';
        if (typingIndicator) typingIndicator.style.display = 'block';
        scrollMessagesToBottom();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify({ message: message })
            });
            
            if (response.status === 401) {
                window.location.reload();
                return;
            }

            const data = await response.json();
            if (typingIndicator) typingIndicator.style.display = 'none';
            if (data.reply) {
                addMessage(data.reply, 'ai');
            }
            if (data.draft) {
                renderDraftCard(data.draft);
            }
            if (!data.reply && !data.draft) {
                addMessage('Sorry, I encountered an issue processing that.', 'ai');
            }
        } catch (error) {
            if (typingIndicator) typingIndicator.style.display = 'none';
            addMessage('Error connecting to the coach. Please check your connection.', 'ai');
        }
    }

    if (chatSend) {
        chatSend.addEventListener('click', sendMessage);
    }
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
    }
})();
