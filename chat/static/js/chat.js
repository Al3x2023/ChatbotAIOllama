document.addEventListener('DOMContentLoaded', function() {
    // Elementos del DOM
    const chatMessages = document.getElementById('chatMessages');
    const userInput = document.getElementById('userInput');
    const sendButton = document.getElementById('sendButton');
    
    // Estado
    let sessionId = SESSION_ID;
    let esperandoRespuesta = false;
    
    // Funciones
    function agregarMensaje(texto, tipo) {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', tipo);
        
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        contentDiv.textContent = texto;
        
        messageDiv.appendChild(contentDiv);
        chatMessages.appendChild(messageDiv);
        
        // Scroll al último mensaje
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function mostrarTipeando() {
        const tipeandoDiv = document.createElement('div');
        tipeandoDiv.classList.add('message', 'bot', 'tipeando');
        tipeandoDiv.id = 'tipeandoIndicator';
        
        const contentDiv = document.createElement('div');
        contentDiv.classList.add('message-content');
        contentDiv.textContent = '...';
        
        tipeandoDiv.appendChild(contentDiv);
        chatMessages.appendChild(tipeandoDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    function ocultarTipeando() {
        const tipeando = document.getElementById('tipeandoIndicator');
        if (tipeando) {
            tipeando.remove();
        }
    }
    
    async function enviarMensaje() {
        const mensaje = userInput.value.trim();
        
        if (!mensaje || esperandoRespuesta) return;
        
        // Mostrar mensaje del usuario
        agregarMensaje(mensaje, 'user');
        userInput.value = '';
        
        // Mostrar indicador de tipeando
        esperandoRespuesta = true;
        mostrarTipeando();
        
        try {
            const response = await fetch('/api/chat/', {
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
            
            // Ocultar indicador y mostrar respuesta
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
    
    // Función para obtener CSRF token
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
    
    // Event Listeners
    sendButton.addEventListener('click', enviarMensaje);
    
    userInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            enviarMensaje();
        }
    });
    
    // Autoajustar altura del textarea
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (this.scrollHeight) + 'px';
    });
});