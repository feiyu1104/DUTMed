document.addEventListener('DOMContentLoaded', () => {
    const questionInput = document.getElementById('question-input');
    const sendBtn = document.getElementById('send-btn');
    const logsPanel = document.getElementById('logs-panel');
    const logsContent = document.getElementById('logs-content');
    const toggleLogsBtn = document.getElementById('toggle-logs-btn');
    const deepSearchBtn = document.getElementById('deep-search-btn');
    const searchBudgetSelect = document.getElementById('search-budget');
    const chatHistory = document.getElementById('chat-history');
    const contentLayout = document.querySelector('.content-layout'); // Get the new layout container
    const fileUploadInput = document.querySelector('.file-upload-input'); // File upload input element
    const appHeader = document.querySelector('.app-header'); // App header element
    const mainContainer = document.querySelector('.main-container'); // Main container element

    // Auto-resize textarea
    if (questionInput) {
        questionInput.addEventListener('input', () => {
            questionInput.style.height = 'auto'; // Reset height
            questionInput.style.height = (questionInput.scrollHeight) + 'px';
        });
        // Allow Shift+Enter for newline, Enter to send
        questionInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault(); // Prevent newline
                sendBtn.click(); // Trigger send
            }
        });
    }

    if (toggleLogsBtn) {
        toggleLogsBtn.addEventListener('click', () => {
            if (logsPanel.classList.contains('visible')) { // Only toggle if visible
                logsPanel.classList.toggle('collapsed');
                toggleLogsBtn.textContent = logsPanel.classList.contains('collapsed') ? '展开' : '折叠';
            }
        });
    }

    if (deepSearchBtn) {
        // Set initial visual state based on data-enabled attribute
        const initialIsEnabled = deepSearchBtn.dataset.enabled === 'true';
        deepSearchBtn.classList.toggle('active', initialIsEnabled);
        deepSearchBtn.title = `多跳查询已 ${initialIsEnabled ? '开启' : '关闭'}`;
        deepSearchBtn.innerHTML = `<span class="icon">🚀</span> 深度搜索 (多跳)`;

        deepSearchBtn.addEventListener('click', () => {
            // Current state before click (from data-attribute)
            const isCurrentlyEnabled = deepSearchBtn.dataset.enabled === 'true';
            // New state after click
            const newEnabledState = !isCurrentlyEnabled;

            deepSearchBtn.dataset.enabled = newEnabledState;
            deepSearchBtn.classList.toggle('active', newEnabledState);
            deepSearchBtn.title = `多跳查询已${newEnabledState ? '开启' : '关闭'}`;
            // 按钮文字始终改变
            deepSearchBtn.innerHTML = `<span class="icon">🚀</span> 深度搜索 (${newEnabledState ? '多跳' : '单跳'})`;
        });
    }

    function displayLoading(show) {
        sendBtn.disabled = show;
        if (show) {
            sendBtn.innerHTML = `<span class="spinner"></span>`;
        } else {
            sendBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="24" height="24"><path d="M3.478 2.405a.75.75 0 00-.926.94l2.432 7.905H13.5a.75.75 0 010 1.5H4.984l-2.432 7.905a.75.75 0 00.926.94 60.519 60.519 0 0018.445-8.986.75.75 0 000-1.218A60.517 60.517 0 003.478 2.405z" /></svg>`;
        }
    }

    let thinkingMessageElement = null; // To keep track of the "thinking..." message
    let chatActivated = false; // Flag to track if chat has been activated

    // Function to hide intro and expand chat area
    function activateChat() {
        if (!chatActivated) {
            chatActivated = true;
            if (appHeader) {
                appHeader.classList.add('chat-active');
            }
            if (mainContainer) {
                mainContainer.classList.add('chat-active');
            }
        }
    }


    // File upload handling
    if (fileUploadInput) {
        fileUploadInput.addEventListener('change', async (event) => {
            const file = event.target.files[0];
            if (!file) return;

            // Check file type
            const allowedTypes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/bmp', 'image/tiff'];
            if (!allowedTypes.includes(file.type)) {
                addChatMessage("不支持的文件类型。请上传PNG、JPG、JPEG、GIF、BMP或TIFF格式的图片。", 'error');
                fileUploadInput.value = '';
                return;
            }

            // Activate chat mode
            activateChat();

            // Show processing message
            addChatMessage("正在上传并处理图像，请稍候...", 'assistant', true);

            try {
                // Create FormData and upload image file
                const formData = new FormData();
                formData.append('image', file);

                const response = await fetch('/upload_image', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (result.success) {
                    // Remove thinking message
                    if (thinkingMessageElement) {
                        thinkingMessageElement.remove();
                        thinkingMessageElement = null;
                    }

                    // Add user uploaded image to chat history (right side, blue)
                    const userImageHtml = `
                        <div class="user-image-upload">
                            <p>上传的图像：</p>
                            <img src="${result.original_image}" alt="上传的图像" class="uploaded-image">
                        </div>
                    `;
                    addChatMessage(userImageHtml, 'user');

                    // Add system segmentation result (left side, assistant)
                    const systemResultHtml = `
                        <div class="segmentation-result">
                            <p>图像分割结果：</p>
                            <div class="segmented-image-container">
                                <img src="${result.segmented_image}" alt="分割结果" class="segmented-image">
                            </div>
                        </div>
                    `;
                    addChatMessage(systemResultHtml, 'assistant');

                    // Add medical image description as plain text (left side, assistant)
                    if (result.description) {
                        addChatMessage(result.description, 'assistant');
                    }

                } else {
                    // Show error message
                    if (thinkingMessageElement) {
                        thinkingMessageElement.classList.remove('thinking');
                        thinkingMessageElement.innerHTML = `图像分割失败: ${result.error || '未知错误'}<br><small>建议：请上传清晰的图像文件，支持PNG、JPG、JPEG、GIF、BMP、TIFF格式</small>`;
                        thinkingMessageElement = null;
                    }
                }
            } catch (error) {
                console.error('Image upload error:', error);
                if (thinkingMessageElement) {
                    thinkingMessageElement.classList.remove('thinking');
                    thinkingMessageElement.innerHTML = `图像上传失败: ${error.message}<br><small>建议：检查网络连接，重新选择图像文件</small>`;
                    thinkingMessageElement = null;
                }
            }

            // Reset file input
            fileUploadInput.value = '';
        });
    }

    function addChatMessage(message, type = 'assistant', isThinkingPlaceholder = false) {
        if (isThinkingPlaceholder) {
            if (thinkingMessageElement) thinkingMessageElement.remove(); // Remove old one if exists
            const messageDiv = document.createElement('div');
            messageDiv.classList.add('message', 'assistant-message', 'thinking');
            messageDiv.innerHTML = `<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span> ${message}`;
            chatHistory.appendChild(messageDiv);
            thinkingMessageElement = messageDiv; // Store reference
        } else {
            if (thinkingMessageElement && type === 'assistant') {
                // Replace thinking message with actual answer
                thinkingMessageElement.classList.remove('thinking');
                let formattedMessage = message.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                formattedMessage = formattedMessage.replace(/\*(.*?)\*/g, '<em>$1</em>');
                formattedMessage = formattedMessage.replace(/`(.*?)`/g, '<code>$1</code>');
                formattedMessage = formattedMessage.replace(/\n/g, '<br>');
                thinkingMessageElement.innerHTML = formattedMessage;
                thinkingMessageElement = null; // Clear reference
            } else {
                const messageDiv = document.createElement('div');
                messageDiv.classList.add('message', type === 'user' ? 'user-message' : 'assistant-message');
                 if (type === 'error') messageDiv.classList.add('error-message');

                let formattedMessage = message.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                formattedMessage = formattedMessage.replace(/\*(.*?)\*/g, '<em>$1</em>');
                formattedMessage = formattedMessage.replace(/`(.*?)`/g, '<code>$1</code>');
                formattedMessage = formattedMessage.replace(/\n/g, '<br>');
                messageDiv.innerHTML = formattedMessage;
                chatHistory.appendChild(messageDiv);
            }
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    if (sendBtn) {
        sendBtn.addEventListener('click', async () => {
            const question = questionInput.value.trim();
            if (!question) return;

            // Activate chat mode
            activateChat();

            // 1. Show and prepare logs panel
            contentLayout.classList.add('logs-active'); // Activate two-column layout
            logsPanel.classList.add('visible');       // Make logs panel visible
            logsPanel.classList.remove('collapsed');  // Ensure it's expanded
            toggleLogsBtn.textContent = '折叠';
            logsContent.innerHTML = '';               // Clear previous logs

            // 2. Clear previous chat messages (except user's new question)
            // chatHistory.innerHTML = ''; // Don't clear, append user message

            // 3. Add user question to chat (only if not triggered by voice input)
            addChatMessage(question, 'user');



            // 4. Add "Thinking..." placeholder for assistant's answer
            addChatMessage("DUTMed 正在思考...", 'assistant', true);

            displayLoading(true); // Disable send button, show spinner

            const enableMultiHop = deepSearchBtn ? deepSearchBtn.dataset.enabled === 'true' : true;
            const searchBudget = searchBudgetSelect ? searchBudgetSelect.value : 'Deeper';

            try {
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', },
                    body: JSON.stringify({ question, enable_multi_hop: enableMultiHop, search_budget: searchBudget, }),
                });

                if (!response.ok) {
                     const errorData = await response.json().catch(() => ({ error: "Unknown server error" }));
                     addChatMessage(`错误: ${response.status} ${response.statusText}. ${errorData.error || ''}`, 'error');
                     displayLoading(false);
                     logsPanel.classList.add('collapsed'); // Collapse logs on error
                     toggleLogsBtn.textContent = '展开';
                     if (thinkingMessageElement) thinkingMessageElement.remove(); // Remove "thinking" message
                     return;
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let finishedProcessing = false; // Renamed for clarity

                function processStream() {
                    reader.read().then(({ done, value }) => {
                        if (done) {
                            if (!finishedProcessing) {
                                displayLoading(false);
                                console.warn("Stream ended without a 'finished' message.");
                                logsPanel.classList.add('collapsed');
                                toggleLogsBtn.textContent = '展开';
                                if (thinkingMessageElement) thinkingMessageElement.innerHTML = "Stream ended."; // Update thinking message
                            }
                            return;
                        }

                        const chunk = decoder.decode(value, { stream: true });
                        const messages = chunk.split('\n\n');

                        messages.forEach(message => {
                            if (message.startsWith('data: ')) {
                                try {
                                    const jsonData = JSON.parse(message.substring(5).trim());

                                    if (jsonData.type === 'log_html') {
                                        const logEntry = document.createElement('div');
                                        logEntry.innerHTML = jsonData.content;
                                        logsContent.appendChild(logEntry);
                                        if (!logsPanel.classList.contains('collapsed')) {
                                            logsContent.scrollTop = logsContent.scrollHeight;
                                        }
                                    } else if (jsonData.type === 'answer') {
                                        // Replace "Thinking..." with the actual answer
                                        addChatMessage(jsonData.content, 'assistant');
                                    } else if (jsonData.type === 'error') {
                                         addChatMessage(`系统错误: ${jsonData.content}`, 'error');
                                         finishedProcessing = true;
                                         displayLoading(false);
                                         logsPanel.classList.add('collapsed');
                                         toggleLogsBtn.textContent = '展开';
                                         if (thinkingMessageElement) thinkingMessageElement.remove();

                                    } else if (jsonData.type === 'finished') {
                                         finishedProcessing = true;
                                         displayLoading(false);
                                         logsPanel.classList.add('collapsed');
                                         toggleLogsBtn.textContent = '展开';
                                         // If no answer was received but finished, remove "thinking"
                                         if (thinkingMessageElement) thinkingMessageElement.remove();
                                    }
                                } catch (e) { console.error('Error parsing SSE message:', e, message); }
                            }
                        });

                        if (!finishedProcessing) {
                           processStream();
                        } else {
                            console.log("Processing finished and UI updated.");
                        }

                    }).catch(error => {
                        console.error('Stream reading error:', error);
                         addChatMessage(`Stream reading error: ${error}`, 'error');
                         displayLoading(false);
                    });
                }
                processStream();

            } catch (error) {
                console.error('Error sending question fetch request:', error);
                 addChatMessage(`Failed to send question: ${error}`, 'error');
                 displayLoading(false);
            }

            questionInput.value = '';
            questionInput.style.height = 'auto';
        });
    }

});