(function() {
    // ========= CONFIGURACIÓN =========
    // Cambia esta URL por la de tu API (puede ser relativa si está en el mismo dominio)
    const API_URL = '/api/chat/';  // O la URL absoluta si es otro dominio: "https://tudominio.com/api/chat/"
    
    // ========= INYECTAR CSS =========
    const style = document.createElement('style');
    style.textContent = `
        /* Estilos del widget flotante */
        .uaemex-widget-btn {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 60px;
            height: 60px;
            background-color: #006241;
            border-radius: 50%;
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            transition: transform 0.2s;
            font-size: 28px;
        }
        .uaemex-widget-btn:hover {
            transform: scale(1.05);
        }
        .uaemex-widget-window {
            position: fixed;
            bottom: 90px;
            right: 20px;
            width: 380px;
            height: 550px;
            background: white;
            border-radius: 15px;
            box-shadow: 0 5px 25px rgba(0,0,0,0.3);
            display: none;
            flex-direction: column;
            overflow: hidden;
            z-index: 9999;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            border: 1px solid #ddd;
        }
        .uaemex-widget-header {
            background: #006241;
            color: white;
            padding: 15px;
            font-weight: bold;
            text-align: center;
            position: relative;
        }
        .uaemex-widget-close {
            position: absolute;
            right: 15px;
            top: 15px;
            cursor: pointer;
            background: none;
            border: none;
            color: white;
            font-size: 20px;
            font-weight: bold;
        }
        .uaemex-widget-messages {
            flex: 1;
            overflow-y: auto;
            padding: 15px;
            background: #f5f5f5;
            display: flex;
            flex-direction: column;
        }
        .message {
            margin-bottom: 12px;
            display: flex;
        }
        .message.user {
            justify-content: flex-end;
        }
        .message.bot {
            justify-content: flex-start;
        }
        .message-content {
            max-width: 80%;
            padding: 10px 14px;
            border-radius: 18px;
            font-size: 14px;
            line-height: 1.4;
            word-wrap: break-word;
        }
        .user .message-content {
            background: #006241;
            color: white;
        }
        .bot .message-content {
            background: #e0e0e0;
            color: black;
        }
        /* Indicador de tipeando (puntos animados) */
        .tipeando .message-content {
            background: #e0e0e0;
            padding: 10px 18px;
        }
        .tipeando .message-content::after {
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
            display: inline-block;
            width: 24px;
            text-align: left;
        }
        @keyframes dots {
            0%, 20% { content: ''; }
            40% { content: '.'; }
            60% { content: '..'; }
            80%, 100% { content: '...'; }
        }
        .uaemex-widget-input-area {
            display: flex;
            padding: 12px;
            border-top: 1px solid #ccc;
            background: white;
            align-items: flex-end;
        }
        .uaemex-widget-input {
            flex: 1;
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 20px;
            font-family: inherit;
            resize: none;
            font-size: 14px;
        }
        .uaemex-widget-send {
            margin-left: 10px;
            background: #006241;
            color: white;
            border: none;
            border-radius: 20px;
            padding: 8px 18px;
            cursor: pointer;
            font-weight: bold;
        }
    `;
    document.head.appendChild(style);

    // ========= INYECTAR HTML =========
    const widgetHtml = `
        <div id="uaemexWidgetRoot">
            <div class="uaemex-widget-btn" id="uaemexChatButton">💬</div>
            <div class="uaemex-widget-window" id="uaemexChatWindow">
                <div class="uaemex-widget-header">
                    Asistente UAEMEX
                    <button class="uaemex-widget-close" id="uaemexCloseBtn">✕</button>
                </div>
                <div class="uaemex-widget-messages" id="uaemexMessages">
                    <div class="message bot">
                        <div class="message-content">¡Hola! Soy el asistente virtual de la UAEMEX. ¿En qué puedo ayudarte?</div>
                    </div>
                </div>
                <div class="uaemex-widget-input-area">
                    <textarea class="uaemex-widget-input" id="uaemexInput" rows="1" placeholder="Escribe tu pregunta..."></textarea>
                    <button class="uaemex-widget-send" id="uaemexSendBtn">Enviar</button>
                </div>
            </div>
        </div>
    `;
    const container = document.createElement('div');
    container.innerHTML = widgetHtml;
    document.body.appendChild(container);

    // ========= OBTENER REFERENCIAS A ELEMENTOS =========
    const chatMessages = document.getElementById('uaemexMessages');
    const userInput = document.getElementById('uaemexInput');
    const sendButton = document.getElementById('uaemexSendBtn');
    const chatButton = document.getElementById('uaemexChatButton');
    const chatWindow = document.getElementById('uaemexChatWindow');
    const closeBtn = document.getElementById('uaemexCloseBtn');

    // Estado
    let sessionId = localStorage.getItem('uaemex_session_id');
    if (!sessionId) {
        sessionId = 'widget_' + Date.now() + '_' + Math.random().toString(36).substr(2, 8);
        localStorage.setItem('uaemex_session_id', sessionId);
    }
    let esperandoRespuesta = false;

    // Funciones auxiliares
    function agregarMensaje(texto, tipo) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', tipo);
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        contentDiv.textContent = texto;
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function mostrarTipeando() {
        const tipeandoDiv = document.createElement('div');
        tipeandoDiv.classList.add('message', 'bot', 'tipeando');
        tipeandoDiv.id = 'tipeandoIndicator';
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        contentDiv.textContent = '';
        tipeandoDiv.appendChild(contentDiv);
        chatMessages.appendChild(tipeandoDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function ocultarTipeando() {
        const tipeando = document.getElementById('tipeandoIndicator');
        if (tipeando) tipeando.remove();
    }

    // Función para obtener CSRF token (si tu API lo requiere)
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Enviar mensaje
    async function enviarMensaje() {
        const mensaje = userInput.value.trim();
        if (!mensaje || esperandoRespuesta) return;

        agregarMensaje(mensaje, 'user');
        userInput.value = '';
        userInput.style.height = 'auto';

        esperandoRespuesta = true;
        mostrarTipeando();

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    mensaje: mensaje,
                    session_id: sessionId
                })
            });
            const data = await response.json();
            ocultarTipeando();
            if (data.respuesta) {
                agregarMensaje(data.respuesta, 'bot');
            } else {
                agregarMensaje('Lo siento, no entendí tu pregunta.', 'bot');
            }
        } catch (error) {
            console.error('Error:', error);
            ocultarTipeando();
            agregarMensaje('Error de conexión. Intenta de nuevo.', 'bot');
        } finally {
            esperandoRespuesta = false;
        }
    }

    // Autoajuste del textarea
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });

    // Eventos
    sendButton.addEventListener('click', enviarMensaje);
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            enviarMensaje();
        }
    });
    chatButton.addEventListener('click', () => {
        chatWindow.style.display = 'flex';
    });
    closeBtn.addEventListener('click', () => {
        chatWindow.style.display = 'none';
    });
})();