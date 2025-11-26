import { BrowserRouter as Router, Routes, Route, Link, useNavigate } from "react-router-dom";
import "./App.css"; // Using external CSS
import { useState, useRef, useEffect } from "react";

// TypeScript declarations for Web Speech API
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

// Optimized Resend Button Component
interface ResendButtonProps {
  onResend: () => Promise<void>;
  countdown: number;
  maxCountdown?: number;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  children?: React.ReactNode;
}

function ResendButton({ 
  onResend, 
  countdown, 
  maxCountdown = 60, 
  loading = false, 
  disabled = false,
  className = "",
  children 
}: ResendButtonProps) {
  const [isResending, setIsResending] = useState(false);
  const [error, setError] = useState(false);

  const handleResend = async () => {
    if (countdown > 0 || loading || disabled || isResending) return;
    
    setIsResending(true);
    setError(false);
    
    try {
      await onResend();
    } catch (err) {
      setError(true);
      // Remove error state after animation
      setTimeout(() => setError(false), 500);
    } finally {
      setIsResending(false);
    }
  };

  const isDisabled = countdown > 0 || loading || disabled || isResending;
  const progressPercentage = countdown > 0 ? ((countdown / maxCountdown) * 100) : 0;
  
  const buttonClass = `auth-secondary-button ${loading || isResending ? 'loading' : ''} ${error ? 'error' : ''} ${countdown === 0 && !loading && !disabled ? 'ready' : ''} ${className}`;

  return (
    <div className="resend-button-container">
      <button
        type="button"
        className={buttonClass}
        onClick={handleResend}
        disabled={isDisabled}
        aria-label={countdown > 0 ? `Resend available in ${countdown} seconds` : "Resend OTP code"}
      >
        {loading || isResending ? (
          <>
            <span>Resending...</span>
          </>
        ) : countdown > 0 ? (
          <>
            <svg className="resend-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z" fill="currentColor"/>
            </svg>
            <span>Resend in {countdown}s</span>
          </>
        ) : (
          <>
            <svg className="resend-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z" fill="currentColor"/>
            </svg>
            <span>{children || "Resend Code"}</span>
          </>
        )}
      </button>
      
      {countdown > 0 && (
        <>
          <div className="countdown-bar">
            <div 
              className="countdown-fill" 
              style={{ width: `${progressPercentage}%` }}
            ></div>
          </div>
          <div className="countdown-text">
            {countdown} seconds remaining
          </div>
        </>
      )}
    </div>
  );
}

// Chat component
function ChatTab() {
  const detectMobileDevice = () =>
    typeof navigator !== "undefined" &&
    /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent);
  const [isMobileDevice] = useState<boolean>(detectMobileDevice);
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [messages, setMessages] = useState<Array<{text: string, isUser: boolean}>>([
    { text: "Hello! I'm your AI Legal Assistant. Ask me any legal question and I'll help you with research, analysis, or guidance.", isUser: false }
  ]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState<boolean>(() => !detectMobileDevice()); // Auto-speak off by default on mobile
  const [voiceLanguage, setVoiceLanguage] = useState<'en' | 'hi'>('en');
  const [availableVoices, setAvailableVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [ttsSupported, setTtsSupported] = useState<boolean>(false);
  const [sttSupported, setSttSupported] = useState<boolean>(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const speechRef = useRef<SpeechSynthesisUtterance | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (autoSpeak) {
      speakLastMessage();
    } else {
      stopSpeaking();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSpeak]);

  useEffect(() => {
    if (!autoSpeak) {
      stopSpeaking();
      return;
    }
    speakLastMessage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceLanguage]);

  const toggleChat = () => {
    if (isOpen) {
      setIsOpen(false);
    } else {
      setIsOpen(true);
      setIsMinimized(false);
    }
  };

  const toggleMinimize = () => {
    setIsMinimized(!isMinimized);
  };

  // Initialize speech recognition
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hasRecognition = 'webkitSpeechRecognition' in window || 'SpeechRecognition' in window;
    setSttSupported(hasRecognition);
    if (!hasRecognition) {
      recognitionRef.current = null;
      return;
    }
    
    if (hasRecognition) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = false;
      recognitionRef.current.interimResults = false;
      
      // Set language for speech recognition
      if (voiceLanguage === 'en') {
        recognitionRef.current.lang = 'en-US';
      } else {
        // For Hindi, try hi-IN first, fallback to en-IN if not available
        recognitionRef.current.lang = 'hi-IN';
      }
      
      recognitionRef.current.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        console.log(`🎤 Recognized: "${transcript}" in ${voiceLanguage}`);
        setInputText(transcript);
        setIsListening(false);
      };
      
      recognitionRef.current.onerror = (event: any) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
        
        // If Hindi recognition fails, try with Indian English as fallback
        if (voiceLanguage === 'hi' && event.error === 'not-allowed') {
          console.log('Trying fallback to Indian English for speech recognition...');
          recognitionRef.current.lang = 'en-IN';
        }
      };
      
      recognitionRef.current.onend = () => {
        setIsListening(false);
      };
    }
  }, [voiceLanguage]);

  // Initialize speech synthesis
  useEffect(() => {
    if (typeof window === "undefined") return;
    if ('speechSynthesis' in window) {
      setTtsSupported(true);
      const synth = window.speechSynthesis;
      speechRef.current = null;

      const handleVoicesChanged = () => {
        const voices = synth.getVoices();
        setAvailableVoices(voices);
      };

      // Populate voices immediately (on some browsers this returns empty until event fires)
      handleVoicesChanged();

      if (typeof synth.addEventListener === "function") {
        synth.addEventListener("voiceschanged", handleVoicesChanged);
        return () => {
          synth.removeEventListener("voiceschanged", handleVoicesChanged);
        };
      } else {
        const originalHandler = synth.onvoiceschanged;
        const voicesChangedHandler = () => {
          handleVoicesChanged();
          if (typeof originalHandler === "function") {
            originalHandler.call(synth, new Event("voiceschanged"));
          }
        };
        synth.onvoiceschanged = voicesChangedHandler;
        return () => {
          if (synth.onvoiceschanged === voicesChangedHandler) {
            synth.onvoiceschanged = originalHandler ?? null;
          }
        };
      }
    } else {
      setTtsSupported(false);
    }
  }, []);

  const startListening = () => {
    if (!sttSupported) {
      alert("Voice input is not supported in this browser.");
      return;
    }
    if (recognitionRef.current && !isListening) {
      setIsListening(true);
      recognitionRef.current.start();
    }
  };

  const stopListening = () => {
    if (recognitionRef.current && isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    }
  };

  const speakText = (text: string, force = false) => {
    if ((!autoSpeak && !force) || !ttsSupported || !('speechSynthesis' in window)) return; // Respect auto-speak toggle or unsupported browsers

    const synth = window.speechSynthesis;
    synth.cancel(); // Stop any ongoing speech before starting new one

    const utterance = new SpeechSynthesisUtterance(text);
    speechRef.current = utterance;
    utterance.lang = voiceLanguage === 'en' ? 'en-US' : 'hi-IN';

    // Get available voices and set appropriate voice
    const voices = availableVoices.length ? availableVoices : synth.getVoices();
    let preferredVoice: SpeechSynthesisVoice | undefined;
    
    if (voiceLanguage === 'en') {
      // For English, prefer US English voices
      preferredVoice = voices.find(voice => 
        voice.lang.toLowerCase().startsWith('en-us') && voice.name.toLowerCase().includes('us')
      ) || voices.find(voice => voice.lang.toLowerCase().startsWith('en'));
    } else {
      // For Hindi, prefer Hindi voices, fallback to Indian English
      preferredVoice = voices.find(voice => 
        voice.lang.toLowerCase().startsWith('hi-in') && voice.name.toLowerCase().includes('hindi')
      ) || voices.find(voice => 
        voice.lang.toLowerCase().startsWith('hi-in')
      ) || voices.find(voice => 
        voice.lang.toLowerCase().startsWith('en-in') && voice.name.toLowerCase().includes('india')
      ) || voices.find(voice => voice.lang.toLowerCase().startsWith('en-in'));
    }
    
    if (preferredVoice) {
      utterance.voice = preferredVoice;
      console.log(`🎤 Using voice: ${preferredVoice.name} (${preferredVoice.lang}) for ${voiceLanguage}`);
    } else if (voices.length > 0) {
      utterance.voice = voices[0];
      console.log(`⚠️ Using fallback voice: ${voices[0].name} (${voices[0].lang})`);
    } else {
      console.warn("No speech synthesis voices available. Browser may not support TTS.");
    }
    
    // Set speech rate and pitch for better Hindi pronunciation
    if (voiceLanguage === 'hi') {
      utterance.rate = 0.85; // Slightly slower for Hindi for better clarity
      utterance.pitch = 1.1; // Slightly higher pitch for Hindi
      utterance.volume = 0.9; // Slightly louder for Hindi
    } else {
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      utterance.volume = 0.85;
    }
    
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);

    synth.speak(utterance);
  };

  const speakLastMessage = (force = false) => {
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && !lastMessage.isUser) {
      speakText(lastMessage.text, force);
    }
  };

  const stopSpeaking = () => {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
      speechRef.current = null;
    }
  };

  const sendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isLoading) return;

    const userMessage = { text: inputText, isUser: true };
    setMessages(prev => [...prev, userMessage]);
    const question = inputText.trim();
    setInputText("");
    setIsLoading(true);

    try {
      // Send to AI backend
      const form = new FormData();
      form.append("action", "legal-research");
      form.append("text", question);
      form.append("language", voiceLanguage); // Use voice language for AI response

      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/process`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} - ${res.statusText}`);
      }

      const data = await res.json();
      const aiResponse = { 
        text: data.result || "I apologize, but I couldn't generate a response at the moment. Please try again.", 
        isUser: false 
      };
      setMessages(prev => [...prev, aiResponse]);
      
      // Auto-speak the AI response
      speakText(aiResponse.text);
    } catch (err: any) {
      console.error("Chat error:", err);
      let errorMessage = "I'm sorry, I'm having trouble connecting to my AI system right now. Please try again later.";
      
      if (err.message.includes("fetch")) {
        errorMessage = "Cannot connect to the AI server. Please check if the backend is running.";
      }
      
      const errorResponse = { 
        text: errorMessage, 
        isUser: false 
      };
      setMessages(prev => [...prev, errorResponse]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-tab">
      <button 
        className={`chat-button ${isMinimized ? 'minimized' : ''}`}
        onClick={toggleChat}
      >
        <span className="chat-icon">💬</span>
        <span className="chat-text">Legal Chat</span>
        <span className="chat-status">AI Ready</span>
      </button>
      
      <div className={`chat-panel ${!isOpen ? 'hidden' : ''} ${isMinimized ? 'minimized' : ''}`}>
        <div className="chat-header">
          <div className="chat-header-content">
            <span className="chat-title">🤖 AI Legal Assistant</span>
            <span className="chat-subtitle">
              Powered by Gemini AI
            </span>
          </div>
          <button onClick={toggleMinimize} className="minimize-btn">
            {isMinimized ? '🔽' : '🔼'}
          </button>
        </div>
        
        {!isMinimized && (
          <>
            <div className="chat-messages">
              {messages.map((msg, index) => (
                <div 
                  key={index} 
                  className={`chat-message ${msg.isUser ? 'user-message' : 'ai-message'}`}
                  style={{
                    animation: `slideIn 0.3s ease-out ${index * 0.1}s both`
                  }}
                >
                  <div className="message-avatar">
                    {msg.isUser ? '👤' : '🤖'}
                  </div>
                  <div className="message-content">
                    {msg.text}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="chat-message ai-message loading-message">
                  <div className="message-avatar">🤖</div>
                  <div className="message-content">
                    <div className="typing-indicator">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                    <span className="loading-text">AI is thinking...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            
            <form onSubmit={sendMessage} className="chat-input">
                          <div className="voice-controls">
              <div className="voice-language-selector">
                <button
                  type="button"
                  className={`voice-lang-btn ${voiceLanguage === 'en' ? 'active' : ''}`}
                  onClick={() => setVoiceLanguage('en')}
                  title="Switch to English Speech"
                >
                  🇺🇸 English
                </button>
                <button
                  type="button"
                  className={`voice-lang-btn ${voiceLanguage === 'hi' ? 'active' : ''}`}
                  onClick={() => setVoiceLanguage('hi')}
                  title="हिंदी भाषा में बदलें"
                >
                  🇮🇳 हिंदी
                </button>
              </div>

                <div className="voice-buttons">
                  <button
                    type="button"
                    className={`voice-button ${isListening ? 'listening' : ''}`}
                    onClick={isListening ? stopListening : startListening}
                    disabled={isLoading || !sttSupported}
                    title={sttSupported ? "Voice Input" : "Voice input not supported on this device"}
                  >
                    {isListening ? '🔴' : '🎤'}
                  </button>
                  <button
                    type="button"
                    className={`voice-button ${autoSpeak ? 'active' : ''}`}
                    onClick={() => ttsSupported && setAutoSpeak(!autoSpeak)}
                    disabled={!ttsSupported}
                    title={autoSpeak ? "Auto-speak: ON" : "Auto-speak: OFF"}
                  >
                    {autoSpeak ? '🔊' : '🔇'}
                  </button>
                  <button
                    type="button"
                    className={`voice-button ${isSpeaking ? 'speaking' : ''}`}
                    onClick={isSpeaking ? stopSpeaking : () => speakLastMessage(true)}
                    disabled={isLoading || messages.length === 0 || !ttsSupported}
                    title={isSpeaking ? "Stop Speaking" : "Speak Last Message"}
                  >
                    {isSpeaking ? '⏹️' : '▶️'}
                  </button>
                </div>
              </div>
              {!ttsSupported && (
                <p className="voice-support-hint">
                  🔇 Text-to-speech is not available in this browser. Try a modern browser like Chrome or Edge.
                </p>
              )}
              {!sttSupported && (
                <p className="voice-support-hint">
                  🎤 Voice dictation is unavailable on this device. You can still type your question.
                </p>
              )}
              <div className="input-wrapper">
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder={voiceLanguage === 'en' ? "Ask me any legal question..." : "मुझसे कोई भी कानूनी सवाल पूछें..."}
                  disabled={isLoading}
                  className="chat-input-field"
                />
                <button 
                  type="submit" 
                  disabled={isLoading || !inputText.trim()} 
                  className="send-button"
                >
                  {isLoading ? '⏳' : '🚀'}
                </button>
              </div>
              <div className="input-hint">
                {voiceLanguage === 'en' 
                  ? "💡 Try: 'What makes a contract legally binding?' or 'Employee rights during termination'"
                  : "💡 कोशिश करें: 'कॉन्ट्रैक्ट कानूनी रूप से बाध्यकारी कैसे होता है?' या 'नौकरी से निकालने के दौरान कर्मचारी के अधिकार'"
                }
              </div>
              {isSpeaking && (
                <div className="speaking-indicator">
                  <span>🔊 AI is speaking...</span>
                  <div className="speaking-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                </div>
              )}
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// Document Viewer Component
function DocumentViewer({ content, action, stampValue }: { content: string; action: string; stampValue?: string | null }) {
  const isMobileDevice = typeof navigator !== "undefined" && /android|iphone|ipad|ipod|mobile/i.test(navigator.userAgent);
  // Build styled, print-ready HTML once and reuse for printing and downloading
  const buildStyledHtml = (raw: string) => {
    const title = action.charAt(0).toUpperCase() + action.slice(1).replace('-', ' ');
    // Convert simple markdown-style bold **text** to <strong>
    const mdToHtml = (txt: string) => txt
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1<\/strong>');

    const bodyHtml = raw.split('\n').map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '<br />';
      if (/^\d+\./.test(trimmed)) return `<div class="numbered"><strong>${mdToHtml(trimmed)}<\/strong><\/div>`;
      if (/^[A-Z][A-Z\s]+:?$/.test(trimmed)) return `<h3 class="section-title">${mdToHtml(trimmed.replace(/:$/, ''))}<\/h3>`;
      return `<p class="para">${mdToHtml(trimmed)}<\/p>`;
    }).join('');

    const stampHtml = stampValue ? `
      <div class="stamp-box">
        <div class="stamp-title">STAMP DUTY REQUIREMENT</div>
        <div class="stamp-details">
          <strong>Required Stamp Paper Value:</strong> ₹${stampValue}<br>
          <em>This amount is based on the document type and state regulations.</em>
        </div>
      </div>` : '';

    return `<!doctype html>
        <html>
          <head>
    <meta charset="utf-8" />
    <title>${title} - AI Legal Companion</title>
            <style>
      @page { 
        size: A4; 
        margin: 25mm 20mm 25mm 20mm; 
        @bottom-center { content: "Page " counter(page) " of " counter(pages); }
      }
      html, body { height: 100%; margin: 0; padding: 0; }
      body { 
        font-family: 'Times New Roman', serif; 
        color: #000; 
        line-height: 1.8; 
        font-size: 12pt;
        background: white;
      }
      .page { 
        position: relative; 
        max-width: 800px; 
        margin: 0 auto; 
        padding: 20px;
      }
      .legal-header { 
        text-align: center; 
        border-bottom: 3px solid #000; 
        padding-bottom: 15px; 
        margin-bottom: 30px; 
      }
      .company-name { 
        font-size: 18pt; 
        font-weight: bold; 
        margin-bottom: 5px; 
        text-transform: uppercase;
        letter-spacing: 1px;
      }
      .document-type { 
        font-size: 14pt; 
        font-weight: bold; 
        margin-bottom: 5px; 
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .meta { 
        font-size: 11pt; 
        color: #333; 
        font-style: italic;
      }
      .ref { 
        display: flex; 
        justify-content: space-between; 
        font-size: 11pt; 
        margin: 20px 0 25px 0; 
        border-bottom: 1px solid #ccc;
        padding-bottom: 10px;
      }
      .document-title { 
        font-size: 20pt; 
        font-weight: bold; 
        text-align: center; 
        margin: 25px 0 30px 0; 
        text-transform: uppercase;
        letter-spacing: 1px;
        border-bottom: 2px solid #000;
        padding-bottom: 15px;
      }
      .section-title { 
        font-size: 15pt; 
        font-weight: bold; 
        margin: 25px 0 15px 0; 
        text-transform: uppercase;
        letter-spacing: 0.5px;
        border-bottom: 1px solid #000;
        padding-bottom: 8px;
      }
      .para { 
        text-align: justify; 
        margin: 0 0 15px 0; 
        text-indent: 25px;
        line-height: 1.8;
      }
      .numbered { 
        margin: 12px 0; 
        text-indent: 25px;
        font-weight: 500;
      }
      .stamp-box { 
        border: 3px solid #000; 
        background: #f8f8f8; 
        padding: 20px; 
        margin: 30px 0; 
        text-align: center;
        page-break-inside: avoid;
      }
      .stamp-title { 
        font-size: 16pt; 
        font-weight: bold; 
        margin-bottom: 15px;
        text-transform: uppercase;
        letter-spacing: 1px;
      }
      .stamp-details { 
        font-size: 12pt; 
        line-height: 1.6;
      }
      .signatures { 
        margin-top: 50px; 
        display: flex; 
        justify-content: space-between; 
        gap: 40px;
        page-break-inside: avoid;
      }
      .sig-block { 
        text-align: center; 
        width: 45%; 
      }
      .sig-line { 
        border-bottom: 1px solid #000; 
        margin: 30px 0 8px 0; 
        height: 0; 
        width: 200px;
        display: inline-block;
      }
      .sig-label { 
        font-size: 10pt; 
        color: #333;
        margin-top: 5px;
      }
      .seal { 
        border: 2px dashed #000; 
        border-radius: 8px; 
        padding: 15px; 
        font-size: 11pt; 
        color: #333; 
        margin-top: 10px;
        background: #f9f9f9;
      }
      .witness-section { 
        margin-top: 40px; 
        border-top: 1px solid #000; 
        padding-top: 20px;
        page-break-inside: avoid;
      }
      .witness-title { 
        font-size: 14pt; 
        font-weight: bold; 
        text-align: center; 
        margin-bottom: 25px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }
      .witness-signatures { 
        display: flex; 
        justify-content: space-between; 
        gap: 30px;
      }
      .witness-block { 
        text-align: center; 
        width: 45%;
      }
      .footer { 
        position: fixed; 
        bottom: 15mm; 
        left: 20mm; 
        right: 20mm; 
        font-size: 10pt; 
        color: #555; 
        display: flex; 
        justify-content: space-between;
        border-top: 1px solid #ccc;
        padding-top: 10px;
      }
      .watermark { 
        position: fixed; 
        top: 40%; 
        left: 50%; 
        transform: translate(-50%, -50%) rotate(-20deg); 
        opacity: 0.04; 
        font-size: 80pt; 
        white-space: nowrap; 
        pointer-events: none;
        font-weight: bold;
        color: #000;
      }
                .no-print { display: none; }
      @media screen { 
        .no-print { 
          display: block; 
          position: fixed; 
          right: 16px; 
          bottom: 16px; 
          z-index: 1000;
        }
        .no-print button {
          background: #4f46e5;
          color: white;
          border: none;
          padding: 8px 16px;
          margin: 0 5px;
          border-radius: 4px;
          cursor: pointer;
        }
        .no-print button:hover {
          background: #3730a3;
        }
      }
            </style>
          </head>
          <body>
    <div class="page">
      <div class="legal-header">
        <div class="company-name">AI Legal Companion</div>
        <div class="meta">Generated on ${new Date().toLocaleDateString('en-US', { 
          year: 'numeric', 
          month: 'long', 
          day: 'numeric' 
        })}</div>
      </div>
      <div class="ref">
        <div><strong>Reference No.:</strong> _____________</div>
        <div><strong>Place:</strong> _____________</div>
              </div>
              <div class="content">
        ${stampHtml}
        ${bodyHtml}
              </div>
      <div class="signatures">
        <div class="sig-block">
          <div class="sig-line"></div>
          <div class="sig-label">Authorized Signatory</div>
              </div>
        <div class="sig-block">
          <div class="sig-line"></div>
          <div class="sig-label">Date</div>
        </div>
      </div>
      <div class="witness-section">
        <div class="witness-title">Witnesses</div>
        <div class="witness-signatures">
          <div class="witness-block">
            <div class="sig-line"></div>
            <div class="sig-label">Witness 1</div>
          </div>
          <div class="witness-block">
            <div class="sig-line"></div>
            <div class="sig-label">Witness 2</div>
          </div>
        </div>
      </div>
      <div class="footer">
        <div><strong>AI Legal Companion</strong> - Professional Legal Document Generation</div>
        <div>Page <span class="page-num"></span></div>
      </div>
      <div class="watermark">AI Legal Companion</div>
            </div>
            <div class="no-print">
              <button onclick="window.print()">Print Document</button>
              <button onclick="window.close()">Close</button>
            </div>
          </body>
</html>`;
  };

  const printDocument = () => {
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(buildStyledHtml(content));
      printWindow.document.close();
    }
  };

  const downloadDocument = async () => {
    const html = buildStyledHtml(content);
    const filename = `${action}-${new Date().toISOString().split('T')[0]}.html`;
    const file = new File([html], filename, { type: 'text/html' });

    if (
      isMobileDevice &&
      navigator.canShare &&
      navigator.canShare({ files: [file] })
    ) {
      try {
        await navigator.share({
          files: [file],
          title: 'AI Legal Document',
          text: 'Download the generated legal document.',
        });
        return;
      } catch (shareError) {
        console.warn('Share failed, falling back to download', shareError);
      }
    }

    const element = document.createElement('a');
    const url = URL.createObjectURL(file);
    element.href = url;
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  };

  const downloadPDF = async () => {
    try {
      // Show loading state
      const pdfButton = document.querySelector('.pdf-btn') as HTMLButtonElement;
      if (pdfButton) {
        pdfButton.disabled = true;
        pdfButton.classList.add('loading');
        pdfButton.textContent = 'Generating PDF...';
      }

      const formData = new FormData();
      formData.append('content', content);
      formData.append('action', action);
      if (stampValue) {
        formData.append('stamp_value', stampValue);
      }

      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/generate-pdf`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Failed to generate PDF: ${response.status} ${response.statusText}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${action}-${new Date().toISOString().split('T')[0]}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      // Show success message
      console.log('PDF downloaded successfully');
    } catch (error) {
      console.error('Error downloading PDF:', error);
      alert(`Failed to download PDF: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      // Reset button state
      const pdfButton = document.querySelector('.pdf-btn') as HTMLButtonElement;
      if (pdfButton) {
        pdfButton.disabled = false;
        pdfButton.classList.remove('loading');
        pdfButton.innerHTML = '📋 PDF';
      }
    }
  };

  if (!content.trim()) {
    return (
      <div className="document-placeholder">
        <div className="placeholder-icon">📄</div>
        <h3>Document Preview</h3>
        <p>Submit a request to see the generated document here</p>
      </div>
    );
  }

  return (
    <div className="document-viewer">
      <div className="document-header">
        <h3>Generated Document</h3>
        <div className="document-actions">
          <button onClick={printDocument} className="action-btn print-btn">
            🖨️ Print
          </button>
          <button onClick={downloadDocument} className="action-btn download-btn">
            📄 HTML
          </button>
          <button onClick={downloadPDF} className="action-btn pdf-btn">
            📋 PDF
          </button>
        </div>
      </div>
      
      <div className="document-content">
        {content.split('\n').map((line, index) => {
          if (line.trim() === '') return <br key={index} />;
          
          // Handle numbered lists
          if (line.match(/^\d+\./)) {
            return (
              <div key={index} className="numbered-item">
                <strong>{line}</strong>
              </div>
            );
          }
          
          // Handle section headers
          if (line.match(/^[A-Z][A-Z\s]+:$/)) {
            return <h4 key={index} className="section-header">{line}</h4>;
          }
          
          // Handle regular paragraphs
          return <p key={index} className="document-paragraph">{line}</p>;
        })}
      </div>
    </div>
  );
}

// Reusable processor component
function Processor({ defaultAction, language, setLanguage }: { defaultAction: string; language?: string; setLanguage?: (lang: string) => void }) {
  const [action, setAction] = useState<string>(defaultAction);
  const [localLanguage, setLocalLanguage] = useState<string>(language || "en");
  const [docType, setDocType] = useState<string>("");
  const [details, setDetails] = useState<string>("");
  const [stateIN, setStateIN] = useState<string>("");
  const [text, setText] = useState<string>("");
  const [includeStamp, setIncludeStamp] = useState<boolean>(false);
  const [result, setResult] = useState<string>("");
  const [stampValue, setStampValue] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pdfUrl, setPdfUrl] = useState<string>("");

  // Use the language from props if available, otherwise use local state
  const currentLanguage = language || localLanguage;
  const currentSetLanguage = setLanguage || setLocalLanguage;

  // Handle file selection
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type === "application/pdf") {
      setSelectedFile(file);
      const url = URL.createObjectURL(file);
      setPdfUrl(url);
    } else {
      setSelectedFile(null);
      setPdfUrl("");
    }
  };

  // Cleanup URL when component unmounts or file changes
  useEffect(() => {
    return () => {
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl);
      }
    };
  }, [pdfUrl]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult("");
    setStampValue("");

    try {
      const form = new FormData();
      form.append("action", action);
      if (currentLanguage) form.append("language", currentLanguage);

      // Add file if selected
      if (selectedFile) {
        form.append("file", selectedFile);
      }

      // Add text if provided
      if (text && text.trim()) {
        form.append("text", text.trim());
      }

      // Add document generation fields if needed
      if (action === "generate-document") {
        if (docType.trim()) form.append("doc_type", docType.trim());
        if (details.trim()) form.append("details", details.trim());
        form.append("include_stamp", String(includeStamp));
        if (stateIN.trim()) form.append("state", stateIN.trim());
      }

      // Debug: log what we're sending
      console.log("Sending form data:", {
        action,
        hasFile: !!selectedFile,
        fileName: selectedFile?.name,
        hasText: !!text.trim(),
        textLength: text.trim().length
      });

      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/process`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const msg = await res.text();
        throw new Error(`${res.status} ${res.statusText}\n${msg}`);
      }

      const data = await res.json();
      setResult(data.result || JSON.stringify(data, null, 2));
      if (data.stamp_value) setStampValue(data.stamp_value);
    } catch (err: any) {
      setError(err?.message || "Request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="three-col">
      <div className="card">
        <form onSubmit={onSubmit} className="form-container">
          <div className="form-fields">
            <div className="row">
              <label>Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value)}>
                <option value="summarize">Summarize</option>
                <option value="legal-research">Legal Research</option>
                <option value="check-document">Check Document</option>
                <option value="analyze-risk">Analyze Risk</option>
                <option value="generate-document">Generate Document</option>
              </select>
            </div>

            <div className="row">
              <label>Language</label>
              <select 
                value={currentLanguage} 
                onChange={(e) => currentSetLanguage(e.target.value)}
                className="language-select"
              >
                <option value="en">🇺🇸 English</option>
                <option value="es">🇪🇸 Español (Spanish)</option>
                <option value="fr">🇫🇷 Français (French)</option>
                <option value="de">🇩🇪 Deutsch (German)</option>
                <option value="it">🇮🇹 Italiano (Italian)</option>
                <option value="pt">🇵🇹 Português (Portuguese)</option>
                <option value="ru">🇷🇺 Русский (Russian)</option>
                <option value="zh">🇨🇳 中文 (Chinese)</option>
                <option value="ja">🇯🇵 日本語 (Japanese)</option>
                <option value="ko">🇰🇷 한국어 (Korean)</option>
                <option value="ar">🇸🇦 العربية (Arabic)</option>
                <option value="hi">🇮🇳 हिन्दी (Hindi)</option>
                <option value="bn">🇧🇩 বাংলা (Bengali)</option>
                <option value="tr">🇹🇷 Türkçe (Turkish)</option>
                <option value="nl">🇳🇱 Nederlands (Dutch)</option>
                <option value="pl">🇵🇱 Polski (Polish)</option>
                <option value="sv">🇸🇪 Svenska (Swedish)</option>
                <option value="da">🇩🇰 Dansk (Danish)</option>
                <option value="no">🇳🇴 Norsk (Norwegian)</option>
                <option value="fi">🇫🇮 Suomi (Finnish)</option>
              </select>
            </div>

            <div className="row">
              <label>Upload PDF (optional)</label>
              <input 
                type="file" 
                accept="application/pdf" 
                onChange={handleFileChange}
              />
              {selectedFile && (
                <small style={{ color: '#059669', fontWeight: 500 }}>
                  ✓ Selected: {selectedFile.name}
                </small>
              )}
            </div>

            <div className="row">
              <label>Text (optional)</label>
              <textarea 
                value={text} 
                onChange={(e) => setText(e.target.value)} 
                rows={6} 
                placeholder="Paste legal text or query..." 
              />
            </div>

            {action === "generate-document" && (
              <>
                <div className="row">
                  <label>Document Type</label>
                  <input value={docType} onChange={(e) => setDocType(e.target.value)} placeholder="e.g., Rent Agreement, NDA" />
                </div>
                <div className="row">
                  <label>State (India)</label>
                  <select value={stateIN} onChange={(e) => setStateIN(e.target.value)}>
                    <option value="">Select state (optional)</option>
                    <option value="Delhi">Delhi</option>
                    <option value="Maharashtra">Maharashtra</option>
                    <option value="Karnataka">Karnataka</option>
                    <option value="Tamil Nadu">Tamil Nadu</option>
                    <option value="Uttar Pradesh">Uttar Pradesh</option>
                    <option value="Haryana">Haryana</option>
                    <option value="Gujarat">Gujarat</option>
                    <option value="Rajasthan">Rajasthan</option>
                    <option value="Telangana">Telangana</option>
                    <option value="West Bengal">West Bengal</option>
                    <option value="Punjab">Punjab</option>
                    <option value="Bihar">Bihar</option>
                    <option value="Madhya Pradesh">Madhya Pradesh</option>
                    <option value="Kerala">Kerala</option>
                    <option value="Odisha">Odisha</option>
                    <option value="Assam">Assam</option>
                    <option value="Chhattisgarh">Chhattisgarh</option>
                    <option value="Jharkhand">Jharkhand</option>
                    <option value="Uttarakhand">Uttarakhand</option>
                    <option value="Himachal Pradesh">Himachal Pradesh</option>
                    <option value="Jammu and Kashmir">Jammu and Kashmir</option>
                    <option value="Chandigarh">Chandigarh</option>
                    <option value="Goa">Goa</option>
                  </select>
                </div>
                <div className="row">
                  <label>Details</label>
                  <textarea value={details} onChange={(e) => setDetails(e.target.value)} placeholder="Parties, addresses, rent/fees, dates, jurisdiction, special terms..." />
                </div>
                <div className="row">
                  <label>Include Stamp Paper Estimate</label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input type="checkbox" checked={includeStamp} onChange={(e) => setIncludeStamp(e.target.checked)} />
                    <span style={{ fontSize: 13, color: '#64748b' }}>Adds a Stamp Paper requirement section</span>
                  </div>
                </div>
              </>
            )}
          </div>

          <button type="submit" className="form-submit-btn" disabled={loading}>
            {loading ? "Working..." : "Send to AI"}
          </button>
        </form>
      </div>

      <div className="card">
        {pdfUrl ? (
          <div className="preview-box">
            <iframe src={pdfUrl} title="PDF Preview" />
          </div>
        ) : (
          <div className="preview-placeholder">Select a PDF to preview</div>
        )}
      </div>

      <div className="card">
        {error && <div className="error-message">{error}</div>}
        <DocumentViewer content={
          stampValue ? `Stamp Paper Requirement: ${stampValue}\n\n${result}` : result
        } action={action} stampValue={stampValue} />
      </div>
    </div>
  );
}

// Pages
function Home({ language, setLanguage }: { language: string; setLanguage: (lang: string) => void }) {
  return (
    <div className="content">
      <h2>Welcome to AI Legal Companion 🚀</h2>
      <p>Your AI-powered partner for legal research, summarization, and document generation.</p>
      <Processor defaultAction="summarize" language={language} setLanguage={setLanguage} />
    </div>
  );
}

function Summarizer() {
  return (
    <div className="content">
      <h2>📖 Summarizer</h2>
      <Processor defaultAction="summarize" />
    </div>
  );
}

function Research() {
  return (
    <div className="content">
      <h2>⚖️ Legal Research Assistant</h2>
      <Processor defaultAction="legal-research" />
    </div>
  );
}

function Docs() {
  return (
    <div className="content">
      <h2>📝 Document Generator</h2>
      <Processor defaultAction="generate-document" />
    </div>
  );
}

export default function App() {
  const [language, setLanguage] = useState<string>("en");
  const [token, setToken] = useState<string>(localStorage.getItem("token") || "");
  const [isAdmin, setIsAdmin] = useState(false);
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [adminStats, setAdminStats] = useState<any>(null);
  const [usersList, setUsersList] = useState<any[]>([]);
  
  // New state for user management
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [showDeleteConfirmModal, setShowDeleteConfirmModal] = useState(false);
  const [userToDelete, setUserToDelete] = useState<any>(null);
  const [adminDeleteConfirmation, setAdminDeleteConfirmation] = useState('');
  const [newUserData, setNewUserData] = useState({ username: '', email: '', password: '', isAdmin: false });
  const [adminActionLoading, setAdminActionLoading] = useState(false);
  const [adminMessage, setAdminMessage] = useState({ type: '', text: '' });
  const [currentAdminPage, setCurrentAdminPage] = useState('dashboard'); // Default to dashboard


  const handleLogout = () => {
    setToken("");
    localStorage.removeItem("token");
    setIsAdmin(false);
    setShowAdminPanel(false);
  };

  const fetchAdminStats = async () => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/stats`, {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        setAdminStats(data);
      }
    } catch (error) {
      console.error("Error fetching admin stats:", error);
    }
  };

  const fetchUsersList = async () => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/users`, {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      if (res.ok) {
        const data = await res.json();
        setUsersList(data.users);
      }
    } catch (error) {
      console.error("Error fetching users list:", error);
    }
  };

  // Add new user function
  const addNewUser = async () => {
    if (!newUserData.username || !newUserData.email || !newUserData.password) {
      setAdminMessage({ type: 'error', text: 'Username, email, and password are required' });
      return;
    }

    setAdminActionLoading(true);
    try {
      // Use the new admin endpoint that accepts JSON
      const endpoint = `${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/users/create`;

      const res = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          username: newUserData.username,
          email: newUserData.email,
          password: newUserData.password,
          is_admin: newUserData.isAdmin
        })
      });

      if (res.ok) {
        await res.json();
        setAdminMessage({ type: 'success', text: `User '${newUserData.username}' created successfully!` });
        setNewUserData({ username: '', email: '', password: '', isAdmin: false });
        setShowAddUserModal(false);
        fetchUsersList(); // Refresh the list
      } else {
        const errorData = await res.json();
        setAdminMessage({ type: 'error', text: errorData.detail || errorData.message || 'Failed to create user' });
      }
    } catch (error) {
      setAdminMessage({ type: 'error', text: 'Error creating user' });
    } finally {
      setAdminActionLoading(false);
    }
  };

  // Toggle admin status function
  const handleToggleAdmin = async (user: any) => {
    setAdminActionLoading(true);
    try {
      // Use simpler endpoint structure
      const endpoint = `${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/users/${user.id}/toggle-admin`;
      
      const res = await fetch(endpoint, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json"
        }
      });

      if (res.ok) {
        const action = user.is_admin ? 'removed from' : 'made';
        setAdminMessage({ 
          type: 'success', 
          text: `User '${user.username}' ${action} administrators successfully!` 
        });
        fetchUsersList(); // Refresh the list
      } else {
        const errorData = await res.json();
        console.error('Admin toggle error:', errorData);
        setAdminMessage({ 
          type: 'error', 
          text: errorData.detail || `Failed to ${user.is_admin ? 'remove' : 'make'} admin` 
        });
      }
    } catch (error) {
      console.error('Error updating admin status:', error);
      setAdminMessage({ 
        type: 'error', 
        text: `Network error: ${error instanceof Error ? error.message : 'Unknown error'}` 
      });
    } finally {
      setAdminActionLoading(false);
    }
  };

  // Delete user function
  const deleteUser = async (userId: number) => {
    console.log('Attempting to delete user with ID:', userId, 'Type:', typeof userId);
    
    // Check if we're trying to delete an admin user
    if (userToDelete && userToDelete.is_admin) {
      if (adminDeleteConfirmation !== 'DELETE ADMIN') {
        setAdminMessage({ 
          type: 'error', 
          text: 'To delete an admin user, you must type "DELETE ADMIN" in the confirmation field.' 
        });
        return;
      }
    }
    
    setAdminActionLoading(true);
    try {
      // Build URL with admin confirmation if needed
      let url = `${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/users/${userId}`;
      if (userToDelete && userToDelete.is_admin) {
        url += `?admin_confirmation=${encodeURIComponent(adminDeleteConfirmation)}`;
      }
      
      const res = await fetch(url, {
        method: "DELETE",
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });

      if (res.ok) {
        const data = await res.json();
        setAdminMessage({ type: 'success', text: data.message || 'User deleted successfully!' });
        setShowDeleteConfirmModal(false);
        setUserToDelete(null);
        setAdminDeleteConfirmation(''); // Reset confirmation
        fetchUsersList(); // Refresh the list
      } else {
        const errorData = await res.json();
        console.error('Delete user error:', errorData);
        setAdminMessage({ type: 'error', text: errorData.detail || 'Failed to delete user' });
      }
    } catch (error) {
      setAdminMessage({ type: 'error', text: 'Error deleting user' });
    } finally {
      setAdminActionLoading(false);
    }
  };



  // Handle stat card clicks
  const handleStatClick = (statType: string) => {
    // Add ripple effect
    const event = window.event as MouseEvent;
    if (event) {
      const target = event.currentTarget as HTMLElement;
      const ripple = document.createElement('span');
      ripple.className = 'ripple';
      ripple.style.left = (event.clientX - target.offsetLeft) + 'px';
      ripple.style.top = (event.clientY - target.offsetTop) + 'px';
      target.appendChild(ripple);
      
      setTimeout(() => {
        ripple.remove();
      }, 600);
    }

    // Handle different stat types
    switch (statType) {
      case 'users':
        setAdminMessage({ type: 'success', text: `Total Users: ${adminStats?.total_users || 0} users registered` });
        break;
      case 'new-users':
        setAdminMessage({ type: 'success', text: `🆕 New Users: ${adminStats?.new_users_30_days || 0} users joined in the last 30 days` });
        break;
              case 'searches':
          setAdminMessage({ type: 'success', text: `Total Searches: ${adminStats?.total_searches_30_days || 0} searches performed in the last 30 days` });
          break;
        case 'export':
          setAdminMessage({ type: 'info', text: 'Export functionality not yet implemented.' });
          break;
        case 'refresh':
          setAdminMessage({ type: 'info', text: 'Refreshing statistics...' });
          fetchAdminStats();
          break;
        case 'notifications':
          setAdminMessage({ type: 'info', text: 'Notification functionality not yet implemented.' });
          break;
        default:
          break;
    }

    // Auto-hide message after 3 seconds
    setTimeout(() => {
      setAdminMessage({ type: '', text: '' });
    }, 3000);
  };



  const checkAdminStatus = async () => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/stats`, {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      if (res.ok) {
        setIsAdmin(true);
        console.log("🔧 Admin status detected: true");
      } else {
        setIsAdmin(false);
        console.log("🔧 Admin status detected: false");
      }
    } catch (error) {
      setIsAdmin(false);
      console.log("🔧 Admin status error:", error);
    }
  };

  useEffect(() => {
    if (token) {
              console.log("Checking admin status for token:", token.substring(0, 20) + "...");
      checkAdminStatus();
    } else {
              console.log("No token found, setting admin to false");
      setIsAdmin(false);
    }
  }, [token]);

  // Protected Route Component
  const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
    if (!token) {
      return <Login setToken={setToken} setIsAdmin={setIsAdmin} />;
    }
    return <>{children}</>;
  };

  return (
    <Router>
      {token && (
      <nav>
        <Link to="/">Home</Link>
        <Link to="/summarizer">Summarizer</Link>
        <Link to="/research">Research Assistant</Link>
        <Link to="/docs">Docs Generator</Link>
          {isAdmin && (
            <button 
              onClick={() => {
                setShowAdminPanel(!showAdminPanel);
                if (!showAdminPanel) {
                  fetchAdminStats();
                  fetchUsersList();
                }
              }}
              className="admin-btn"
            >
              {showAdminPanel ? 'Hide Admin' : 'Admin Panel'}
            </button>
          )}

          <button onClick={handleLogout}>Logout</button>
      </nav>
      )}

      <Routes>
        <Route path="/login" element={!token ? <Login setToken={setToken} setIsAdmin={setIsAdmin} /> : <Home language={language} setLanguage={setLanguage} />} />
        <Route path="/signup" element={!token ? <Signup /> : <Home language={language} setLanguage={setLanguage} />} />
        <Route path="/otp-test" element={<OTPTestPage />} />
        <Route path="/" element={<ProtectedRoute><Home language={language} setLanguage={setLanguage} /></ProtectedRoute>} />
        <Route path="/summarizer" element={<ProtectedRoute><Summarizer /></ProtectedRoute>} />
        <Route path="/research" element={<ProtectedRoute><Research /></ProtectedRoute>} />
        <Route path="/docs" element={<ProtectedRoute><Docs /></ProtectedRoute>} />
        <Route path="*" element={!token ? <Login setToken={setToken} setIsAdmin={setIsAdmin} /> : <Home language={language} setLanguage={setLanguage} />} />
      </Routes>

      {token && <ChatTab />}
      
      {showAdminPanel && isAdmin && (
        <div className="admin-panel">
          <div className="admin-header">
            <h2>🔧 Admin Dashboard</h2>
            <button onClick={() => setShowAdminPanel(false)} className="close-btn">×</button>
          </div>
          
          <div className="admin-layout">
            {/* Navigation Sidebar */}
            <div className="admin-sidebar">
              <div className="nav-buttons">
                            <button 
              className={`nav-btn ${currentAdminPage === 'dashboard' ? 'active' : ''}`}
              onClick={() => setCurrentAdminPage('dashboard')}
            >
              Dashboard
            </button>
                <button 
                  className={`nav-btn ${currentAdminPage === 'users' ? 'active' : ''}`}
                  onClick={() => {
                    setCurrentAdminPage('users');
                    if (usersList.length === 0) {
                      fetchUsersList();
                    }
                  }}
                >
                  Users
                </button>
                <button 
                  className={`nav-btn ${currentAdminPage === 'searches' ? 'active' : ''}`}
                  onClick={() => setCurrentAdminPage('searches')}
                >
                  Searches
                </button>
                <button 
                  className={`nav-btn ${currentAdminPage === 'topics' ? 'active' : ''}`}
                  onClick={() => setCurrentAdminPage('topics')}
                >
                  Topics
                </button>
                <button 
                  className={`nav-btn ${currentAdminPage === 'downloads' ? 'active' : ''}`}
                  onClick={() => setCurrentAdminPage('downloads')}
                >
                  Downloads
                </button>
                <button 
                  className={`nav-btn ${currentAdminPage === 'analytics' ? 'active' : ''}`}
                  onClick={() => setCurrentAdminPage('analytics')}
                >
                  Analytics
                </button>
              </div>
            </div>

            {/* Main Content Area */}
            <div className="admin-main-content">
              {adminMessage.text && (
                <div className={`admin-message ${adminMessage.type}`}>
                  {adminMessage.text}
                  <button onClick={() => setAdminMessage({ type: '', text: '' })} className="close-message">×</button>
                </div>
              )}

              {/* Dashboard Page */}
              {currentAdminPage === 'dashboard' && (
                <div className="admin-page">
                  <h3>Overview Statistics</h3>
                  
                  {/* Quick Action Buttons */}
                  <div className="quick-actions">
                    <button className="quick-action-btn" onClick={() => setShowAddUserModal(true)}>
                      Add User
                    </button>
                    <button className="quick-action-btn" onClick={() => handleStatClick('export')}>
                      Export Data
                    </button>
                    <button className="quick-action-btn" onClick={() => handleStatClick('refresh')}>
                      Refresh Stats
                    </button>
                    <button className="quick-action-btn" onClick={() => handleStatClick('notifications')}>
                      Send Notification
                    </button>
                  </div>

                  {adminStats ? (
                    <div className="stats-grid">
                      <div 
                        className="stat-card" 
                        onClick={() => handleStatClick('users')}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === 'Enter' && handleStatClick('users')}
                      >
                        <div className="stat-number">{adminStats.total_users}</div>
                        <div className="stat-label">Total Users</div>
                        <div className="stat-trend">+{adminStats.new_users_today} today</div>
                      </div>
                      <div 
                        className="stat-card" 
                        onClick={() => handleStatClick('new-users')}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === 'Enter' && handleStatClick('new-users')}
                      >
                        <div className="stat-number">{adminStats.new_users_30_days}</div>
                        <div className="stat-label">New Users (30d)</div>
                        <div className="stat-trend">+{adminStats.new_users_7_days} this week</div>
                      </div>
                      <div 
                        className="stat-card" 
                        onClick={() => handleStatClick('searches')}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === 'Enter' && handleStatClick('searches')}
                      >
                        <div className="stat-number">{adminStats.total_searches}</div>
                        <div className="stat-label">Total Searches</div>
                        <div className="stat-trend">+{adminStats.total_searches_today} today</div>
                      </div>
                      <div 
                        className="stat-card" 
                        onClick={() => handleStatClick('admins')}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === 'Enter' && handleStatClick('admins')}
                      >
                        <div className="stat-number">{adminStats.total_admins}</div>
                        <div className="stat-label">Admin Users</div>
                        <div className="stat-trend">System administrators</div>
                      </div>
                    </div>
                  ) : (
                    <div className="loading">Loading statistics...</div>
                  )}
                </div>
              )}

              {/* Users Page */}
{currentAdminPage === 'users' && (
  <div className="admin-page">
    <div className="users-header">
      <h3>User Management</h3>
      <button 
        onClick={() => setShowAddUserModal(true)}
        className="add-user-btn"
      >
        <span className="add-icon">+</span>
        Add New User
      </button>
    </div>
    
    <div className="users-list">
      {usersList.map((user: any) => (
        <div key={user.id} className="user-item">
          <div className="user-info">
            <div className="user-avatar">
              <span className="avatar-text">{user.username.charAt(0).toUpperCase()}</span>
            </div>
            <div className="user-details">
              <span className="user-name">{user.username}</span>
              <span className={`user-role ${user.is_admin ? 'admin' : 'user'}`}>
                {user.is_admin ? 'Admin' : 'User'}
              </span>
            </div>
          </div>
          <div className="user-actions">
            <button 
              onClick={() => handleToggleAdmin(user)}
              className={`toggle-admin-btn ${user.is_admin ? 'remove-admin' : 'make-admin'}`}
              disabled={user.username === 'adminAdmin'}
            >
              {user.is_admin ? 'Remove Admin' : 'Make Admin'}
            </button>
            <button 
              onClick={() => {
                console.log('Setting user to delete:', user);
                setUserToDelete(user);
                setShowDeleteConfirmModal(true);
              }}
              className="delete-btn"
              disabled={user.username === 'adminAdmin'}
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
    
    {usersList.length === 0 && (
      <div className="no-users">
        <div className="no-users-icon">��</div>
        <h4>No Users Found</h4>
        <p>Start by adding your first user to the system.</p>
        <button
          onClick={() => setShowAddUserModal(true)}
          className="add-user-btn primary"
        >
          Add First User
        </button>
      </div>
    )}
  </div>
)}
                            

              {/* Searches Page */}
              {currentAdminPage === 'searches' && (
                <div className="admin-page">
                  <h3>Search Statistics</h3>
                  <div className="search-stats">
                    <div className="stat-item">
                      <h4>Total Searches</h4>
                      <p>{adminStats?.total_searches || 0}</p>
                    </div>
                    <div className="stat-item">
                      <h4>Today's Searches</h4>
                      <p>{adminStats?.total_searches_today || 0}</p>
                    </div>
                    <div className="stat-item">
                      <h4>This Week</h4>
                      <p>{adminStats?.total_searches_7_days || 0}</p>
                    </div>
                    <div className="stat-item">
                      <h4>This Month</h4>
                      <p>{adminStats?.total_searches_30_days || 0}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Topics Page */}
              {currentAdminPage === 'topics' && (
                <div className="admin-page">
                  <h3>Topic Analysis</h3>
                  {adminStats ? (
                    <div className="topics-grid">
                      {adminStats.top_searched_topics && adminStats.top_searched_topics.length > 0 ? (
                        adminStats.top_searched_topics.map((topic: any, index: number) => (
                          <div key={index} className="topic-card">
                            <div className="topic-rank">#{index + 1}</div>
                            <div className="topic-content">
                              <div className="topic-text">{topic.topic}</div>
                              <div className="topic-count">{topic.count} searches</div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="no-activity">No topic data available</div>
                      )}
                    </div>
                  ) : (
                    <div className="loading">Loading topics...</div>
                  )}
                </div>
              )}

              {/* Downloads Page */}
              {currentAdminPage === 'downloads' && (
                <div className="admin-page">
                  <h3>⬇️ Download Statistics</h3>
                  <div className="download-stats">
                    <div className="stat-item">
                      <h4>Total Downloads</h4>
                      <p>Coming Soon</p>
                    </div>
                    <div className="stat-item">
                      <h4>Today's Downloads</h4>
                      <p>Coming Soon</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Analytics Page */}
              {currentAdminPage === 'analytics' && (
                <div className="admin-page">
                  <h3>Detailed Analytics</h3>
                  
                  {adminStats ? (
                    <>
                      {/* System Health & Performance */}
                      <div className="dashboard-section">
                        <h4>🏥 System Health & Performance</h4>
                        <div className="health-grid">
                          <div className="health-card">
                            <div className="health-status">
                              <span className="status-indicator operational"></span>
                              <span>Operational</span>
                            </div>
                            <div className="health-metrics">
                              <p>Uptime: {adminStats.performance_metrics?.uptime_percentage || '99.9%'}</p>
                              <p>Response Time: {adminStats.performance_metrics?.avg_response_time || '1.2s'}</p>
                              <p>Error Rate: {adminStats.performance_metrics?.error_rate || '0.1%'}</p>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Recent Activity & Users */}
                      <div className="dashboard-section">
                        <h4>Recent Activity & Users</h4>
                        <div className="activity-grid">
                          <div className="activity-card">
                                                          <h4>Recent Activity</h4>
                            <div className="activity-list">
                              {adminStats.recent_activity && adminStats.recent_activity.length > 0 ? (
                                adminStats.recent_activity.slice(0, 5).map((activity: any, index: number) => (
                                  <div key={index} className="activity-item">
                                    <div className="activity-icon">
                                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                  </svg>
                                </div>
                                    <div className="activity-content">
                                      <div className="activity-text">{activity.query}</div>
                                      <div className="activity-time">{new Date(activity.timestamp).toLocaleString()}</div>
                                    </div>
                                  </div>
                                ))
                              ) : (
                                <div className="no-activity">No recent activity</div>
                              )}
                            </div>
                          </div>
                          <div className="activity-card">
                                                          <h4>Recent Users</h4>
                            <div className="activity-list">
                              {adminStats.recent_users && adminStats.recent_users.length > 0 ? (
                                adminStats.recent_users.slice(0, 5).map((user: any, index: number) => (
                                  <div key={index} className="activity-item">
                                    <div className="activity-icon">{user.is_admin ? '👑' : '👤'}</div>
                                    <div className="activity-content">
                                      <div className="activity-text">{user.username}</div>
                                      <div className="activity-time">{new Date(user.created_at).toLocaleDateString()}</div>
                                    </div>
                                  </div>
                                ))
                              ) : (
                                <div className="no-activity">No recent users</div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Top Searched Topics */}
                      <div className="dashboard-section">
                        <h4>🔥 Top Searched Topics</h4>
                        <div className="topics-grid">
                          {adminStats.top_searched_topics && adminStats.top_searched_topics.length > 0 ? (
                            adminStats.top_searched_topics.slice(0, 6).map((topic: any, index: number) => (
                              <div key={index} className="topic-card">
                                <div className="topic-rank">#{index + 1}</div>
                                <div className="topic-content">
                                  <div className="topic-text">{topic.topic}</div>
                                  <div className="topic-count">{topic.count} searches</div>
                                </div>
                              </div>
                            ))
                          ) : (
                            <div className="no-activity">No topic data available</div>
                          )}
                        </div>
                      </div>

                      {/* Daily Activity Chart */}
                      <div className="dashboard-section">
                        <h4>Daily Activity</h4>
                        <div className="chart-container">
                          <div className="activity-chart">
                            {adminStats.daily_activity && adminStats.daily_activity.length > 0 ? (
                              adminStats.daily_activity.slice(-7).map((day: any, index: number) => (
                                <div key={index} className="chart-bar">
                                  <div className="bar-fill" style={{ height: `${(day.count / Math.max(...adminStats.daily_activity.map((d: any) => d.count))) * 100}%` }}></div>
                                  <div className="bar-label">{new Date(day.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
                                  <div className="bar-value">{day.count}</div>
                                </div>
                              ))
                            ) : (
                              <div className="no-activity">No activity data available</div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Detailed Analytics Grid */}
                      <div className="dashboard-section">
                        <h4>Detailed Metrics</h4>
                        <div className="analytics-grid">
                          <div className="analytics-card">
                            <h4>User Growth</h4>
                            <div className="analytics-content">
                              <p>Total Users: {adminStats?.total_users || 0}</p>
                              <p>New Users (30 days): {adminStats?.new_users_30_days || 0}</p>
                              <p>New Users (7 days): {adminStats?.new_users_7_days || 0}</p>
                            </div>
                          </div>
                          <div className="analytics-card">
                            <h4>Search Activity</h4>
                            <div className="analytics-content">
                              <p>Total Searches (30 days): {adminStats?.total_searches_30_days || 0}</p>
                              <p>Total Searches (7 days): {adminStats?.total_searches_7_days || 0}</p>
                              <p>Total Searches (Today): {adminStats?.total_searches_today || 0}</p>
                            </div>
                          </div>
                          <div className="analytics-card">
                            <h4>System Health</h4>
                            <div className="analytics-content">
                              <p>Active Users: {adminStats?.performance_metrics?.active_sessions || 0}</p>
                              <p>System Status: Operational</p>
                              <p>Last Updated: {new Date().toLocaleString()}</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="loading">Loading analytics...</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Add User Modal */}
      {showAddUserModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h3>➕ Add New User</h3>
              <button onClick={() => setShowAddUserModal(false)} className="close-btn">×</button>
            </div>
            <div className="modal-content">
              <div className="form-group">
                <label>Username:</label>
                <input
                  type="text"
                  value={newUserData.username}
                  onChange={(e) => setNewUserData({...newUserData, username: e.target.value})}
                  placeholder="Enter username"
                  disabled={adminActionLoading}
                />
              </div>
              <div className="form-group">
                <label>Email:</label>
                <input
                  type="email"
                  value={newUserData.email}
                  onChange={(e) => setNewUserData({...newUserData, email: e.target.value})}
                  placeholder="Enter email address"
                  disabled={adminActionLoading}
                />
              </div>
              <div className="form-group">
                <label>Password:</label>
                <input
                  type="password"
                  value={newUserData.password}
                  onChange={(e) => setNewUserData({...newUserData, password: e.target.value})}
                  placeholder="Enter password"
                  disabled={adminActionLoading}
                />
              </div>
              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={newUserData.isAdmin}
                    onChange={(e) => setNewUserData({...newUserData, isAdmin: e.target.checked})}
                    disabled={adminActionLoading}
                  />
                  Make this user an admin
                </label>
              </div>
              <div className="modal-actions">
                <button
                  onClick={addNewUser}
                  className="primary-btn"
                  disabled={adminActionLoading}
                >
                  {adminActionLoading ? 'Creating...' : 'Create User'}
                </button>
                <button
                  onClick={() => setShowAddUserModal(false)}
                  className="secondary-btn"
                  disabled={adminActionLoading}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {showDeleteConfirmModal && userToDelete && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h3>Confirm Delete</h3>
              <button onClick={() => {
                setShowDeleteConfirmModal(false);
                setAdminDeleteConfirmation(''); // Reset confirmation when closing
              }} className="close-btn">×</button>
            </div>
            <div className="modal-content">
              <div className="delete-warning">
                {userToDelete.is_admin ? (
                  <div className="admin-delete-warning">
                    <div className="warning-icon">⚠️</div>
                    <h4>Admin User Deletion</h4>
                    <p>You are about to delete an <strong>administrator account</strong>.</p>
                    <p>This action cannot be undone and may affect system security.</p>
                    
                    <div className="admin-confirmation">
                      <label htmlFor="admin-confirmation">
                        Type <strong>"DELETE ADMIN"</strong> to confirm:
                      </label>
                      <input
                        id="admin-confirmation"
                        type="text"
                        value={adminDeleteConfirmation}
                        onChange={(e) => setAdminDeleteConfirmation(e.target.value)}
                        placeholder="DELETE ADMIN"
                        className="admin-confirmation-input"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="regular-delete-warning">
                    <p>Are you sure you want to delete user <strong>"{userToDelete.username}"</strong>?</p>
                    <p className="warning">This action cannot be undone!</p>
                  </div>
                )}
              </div>
              
              <div className="modal-actions">
                <button
                  onClick={() => deleteUser(userToDelete.id)}
                  className={`danger-btn ${userToDelete.is_admin ? 'admin-delete' : ''}`}
                  disabled={adminActionLoading || (userToDelete.is_admin && adminDeleteConfirmation !== 'DELETE ADMIN')}
                >
                  {adminActionLoading ? 'Deleting...' : 'Delete User'}
                </button>
                <button
                  onClick={() => {
                    setShowDeleteConfirmModal(false);
                    setAdminDeleteConfirmation(''); // Reset confirmation when canceling
                  }}
                  className="secondary-btn"
                  disabled={adminActionLoading}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Router>
  );
}

function Login({ setToken, setIsAdmin }: { setToken: (t: string) => void; setIsAdmin: (isAdmin: boolean) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [forgotEmail, setForgotEmail] = useState("");
  const [forgotOtp, setForgotOtp] = useState("");
  const [forgotStep, setForgotStep] = useState<'email' | 'otp' | 'reset'>('email');
  const [forgotCountdown, setForgotCountdown] = useState(0);
  const navigate = useNavigate();

  const checkAdminStatus = async (token: string) => {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/admin/stats`, {
        headers: {
          "Authorization": `Bearer ${token}`
        }
      });
      return res.ok;
    } catch (error) {
      return false;
    }
  };

  // Optimized countdown timer for forgot password OTP
  useEffect(() => {
    if (forgotCountdown > 0) {
      const timer = setTimeout(() => {
        setForgotCountdown(prev => {
          if (prev <= 1) {
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [forgotCountdown]);

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (forgotStep === 'email') {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/send-otp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: forgotEmail })
        });

        if (!res.ok) {
          const errorData = await res.json();
          throw new Error(errorData.detail || "Failed to send OTP");
        }

        const data = await res.json();
        setForgotStep('otp');
        setForgotCountdown(60);
        setSuccess("OTP sent successfully! Check your email.");
        
        // In development, show OTP in console
        console.log(`🔐 Forgot password OTP sent to ${forgotEmail}: ${data.otp_code}`);
      } catch (err: any) {
        setError(err?.message || "Failed to send OTP");
      } finally {
        setLoading(false);
      }
      return;
    }

    if (forgotStep === 'otp') {
      setLoading(true);
      setError("");
      try {
        const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/verify-otp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: forgotEmail, otp_code: forgotOtp })
        });

        if (!res.ok) {
          const errorData = await res.json();
          throw new Error(errorData.detail || "OTP verification failed");
        }

        setForgotStep('reset');
        setSuccess("Email verified successfully! You can now reset your password.");
      } catch (err: any) {
        setError(err?.message || "OTP verification failed");
      } finally {
        setLoading(false);
      }
      return;
    }
  };

  const resendForgotOtp = async () => {
    if (forgotCountdown > 0) return;
    
    setLoading(true);
    setError("");
    
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/resend-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: forgotEmail })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to resend OTP");
      }

      const data = await res.json();
      setForgotCountdown(60);
      setSuccess("OTP resent successfully! Check your email.");
      
      // In development, show OTP in console
      console.log(`🔐 Forgot password OTP resent to ${forgotEmail}: ${data.otp_code}`);
    } catch (err: any) {
      setError(err?.message || "Failed to resend OTP");
      throw err; // Re-throw for the ResendButton component to handle
    } finally {
      setLoading(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      console.log("Attempting login for user:", username);
      
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      });
      
      console.log("Login response status:", res.status);
      
      if (!res.ok) {
        let errorMessage = "Login failed";
        try {
          const errorData = await res.json();
          errorMessage = errorData.detail || errorMessage;
        } catch {
          const errorText = await res.text();
          errorMessage = errorText || errorMessage;
        }
        
        if (res.status === 0 || res.status === 500) {
          errorMessage = "Server connection failed. Please check if the backend is running.";
        } else if (res.status === 401) {
          errorMessage = "Invalid username or password";
        } else if (res.status === 403) {
          errorMessage = "Access denied";
        }
        
        throw new Error(errorMessage);
      }
      
      const data = await res.json();
      console.log("Login successful, token received");
      
      localStorage.setItem("token", data.access_token);
      setToken(data.access_token);
      
      // Check if user is admin
      console.log("Checking admin status after login...");
      const isAdmin = await checkAdminStatus(data.access_token);
      console.log("Admin status result:", isAdmin);
      setIsAdmin(isAdmin);
      if (isAdmin) {
        console.log("Admin user logged in");
      } else {
        console.log("User is not admin");
      }
      
      navigate("/");
    } catch (err: any) {
      console.error("Login error:", err);
      setError(err?.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L13.09 8.26L20 9L13.09 9.74L12 16L10.91 9.74L4 9L10.91 8.26L12 2Z" fill="#4f46e5"/>
              <path d="M19 15L19.74 17.74L22.5 18.5L19.74 19.26L19 22L18.26 19.26L15.5 18.5L18.26 17.74L19 15Z" fill="#7c3aed"/>
              <path d="M5 6L5.37 7.37L6.74 7.74L5.37 8.11L5 9.48L4.63 8.11L3.26 7.74L4.63 7.37L5 6Z" fill="#10b981"/>
            </svg>
          </div>
          <h1 className="auth-title">Welcome Back</h1>
          <p className="auth-subtitle">Sign in to your AI Legal Companion account</p>
        </div>
        
        {error && <div className="auth-error">{error}</div>}
        {success && <div className="auth-success">{success}</div>}
        
        {!showForgotPassword ? (
          <>
            <form onSubmit={submit} className="auth-form">
              <div className="auth-input-group">
                <label className="auth-label">Username</label>
                <input
                  type="text"
                  className="auth-input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  required
                />
              </div>
              
              <div className="auth-input-group">
                <label className="auth-label">Password</label>
                <div className="password-input-container">
                  <input
                    type={showPassword ? "text" : "password"}
                    className="auth-input password-input"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    className="auth-password-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>
              
              <button className="auth-button" type="submit" disabled={loading}>
                {loading && <span className="auth-loading"></span>}
                {loading ? "Signing in..." : "Sign In"}
              </button>
            </form>
            
            <div className="auth-actions">
              <button 
                className="auth-secondary-button new-user-btn"
                onClick={() => navigate("/signup")}
                type="button"
              >
                New User
              </button>
            </div>
            
            <div className="auth-link">
              <p>Don't have an account? <Link to="/signup">Sign up</Link></p>
              <p>
                <button 
                  type="button" 
                  className="forgot-password-link"
                  onClick={() => setShowForgotPassword(true)}
                >
                  Forgot your password?
                </button>
              </p>
            </div>
          </>
        ) : (
          /* Forgot Password Form */
          <div className="forgot-password-container">
            <div className="forgot-password-header">
              <button 
                type="button" 
                className="back-to-login-btn"
                onClick={() => {
                  setShowForgotPassword(false);
                  setForgotStep('email');
                  setForgotEmail("");
                  setForgotOtp("");
                  setError("");
                  setSuccess("");
              }}
            >
              ← Back to Login
            </button>
            <h2>Reset Password</h2>
            <p>Enter your email to receive a verification code</p>
          </div>
          
          <form onSubmit={handleForgotPassword} className="auth-form">
            {forgotStep === 'email' && (
              <div className="auth-input-group">
                <label className="auth-label">Email Address</label>
                <input
                  type="email"
                  className="auth-input"
                  value={forgotEmail}
                  onChange={(e) => setForgotEmail(e.target.value)}
                  placeholder="Enter your email address"
                  required
                />
              </div>
            )}
            
            {forgotStep === 'otp' && (
              <div className="auth-input-group">
                <label className="auth-label">Verification Code</label>
                <input
                  type="text"
                  className="auth-input otp-input"
                  value={forgotOtp}
                  onChange={(e) => setForgotOtp(e.target.value)}
                  placeholder="Enter 6-digit code"
                  maxLength={6}
                  required
                />
                <div className="otp-hint">
                  <p>We've sent a 6-digit code to <strong>{forgotEmail}</strong></p>
                  <p>Check your email and enter the code above</p>
                </div>
                
                <div className="auth-actions">
                  <ResendButton
                    onResend={resendForgotOtp}
                    countdown={forgotCountdown}
                    maxCountdown={60}
                    loading={loading}
                  >
                    Resend Code
                  </ResendButton>
                </div>
              </div>
            )}
            
            {forgotStep === 'reset' && (
              <div className="auth-input-group">
                <div className="verification-success">
                  <div className="verification-icon">✅</div>
                  <h3>Email Verified!</h3>
                  <p>Your email has been verified. Please contact support to reset your password.</p>
                </div>
              </div>
            )}
            
            <button className="auth-button" type="submit" disabled={loading}>
              {loading && <span className="auth-loading"></span>}
              {forgotStep === 'email' && (loading ? "Sending..." : "Send Code")}
              {forgotStep === 'otp' && (loading ? "Verifying..." : "Verify Code")}
              {forgotStep === 'reset' && "Contact Support"}
            </button>
          </form>
        </div>
      )}
      </div>
    </div>
  );
}

function Signup() {
  const [step, setStep] = useState<'form' | 'otp'>('form');
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const [countdown, setCountdown] = useState(0);
  const navigate = useNavigate();

  // Optimized countdown timer for OTP resend
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [countdown]);

  const sendOTP = async () => {
    if (!email) {
      setError("Please enter your email address");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/send-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to send OTP");
      }

      const data = await res.json();
      setStep('otp');
      setCountdown(60); // 60 second countdown
      
      // In development, show OTP in console
      console.log(`🔐 OTP sent to ${email}: ${data.otp_code}`);
      
      setSuccess("OTP sent successfully! Check your email.");
    } catch (err: any) {
      setError(err?.message || "Failed to send OTP");
    } finally {
      setLoading(false);
    }
  };

  const verifyOTP = async () => {
    if (!otpCode) {
      setError("Please enter the OTP");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp_code: otpCode })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "OTP verification failed");
      }

      // After OTP verification, automatically create the account
      setSuccess("Email verified successfully! Creating your account...");
      
      const registerRes = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password })
      });
      
      if (!registerRes.ok) {
        const errorData = await registerRes.json();
        throw new Error(errorData.detail || "Account creation failed");
      }
      
      setSuccess("Account created successfully! Redirecting to login...");
      setTimeout(() => {
        navigate("/login");
      }, 2000);
    } catch (err: any) {
      setError(err?.message || "OTP verification failed");
    } finally {
      setLoading(false);
    }
  };

  const resendOTP = async () => {
    if (countdown > 0) return;
    
    setLoading(true);
    setError("");
    
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/resend-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to resend OTP");
      }

      const data = await res.json();
      setCountdown(60);
      setSuccess("OTP resent successfully! Check your email.");
      
      // In development, show OTP in console
      console.log(`🔐 OTP resent to ${email}: ${data.otp_code}`);
    } catch (err: any) {
      setError(err?.message || "Failed to resend OTP");
      throw err; // Re-throw for the ResendButton component to handle
    } finally {
      setLoading(false);
    }
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (step === 'form') {
      if (password !== confirmPassword) {
        setError("Passwords do not match");
        return;
      }
      await sendOTP();
      return;
    }

    if (step === 'otp') {
      await verifyOTP();
      return;
    }


  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L13.09 8.26L20 9L13.09 9.74L12 16L10.91 9.74L4 9L10.91 8.26L12 2Z" fill="#4f46e5"/>
              <path d="M19 15L19.74 17.74L22.5 18.5L19.74 19.26L19 22L18.26 19.26L15.5 18.5L18.26 17.74L19 15Z" fill="#7c3aed"/>
              <path d="M5 6L5.37 7.37L6.74 7.74L5.37 8.11L5 9.48L4.63 8.11L3.26 7.74L4.63 7.37L5 6Z" fill="#10b981"/>
            </svg>
          </div>
          <h1 className="auth-title">
            {step === 'form' && "Create Account"}
            {step === 'otp' && "Verify Email"}
          </h1>
          <p className="auth-subtitle">
            {step === 'form' && "Join AI Legal Companion today"}
            {step === 'otp' && `Enter the OTP sent to ${email}`}
          </p>
        </div>
        
        {error && <div className="auth-error">{error}</div>}
        {success && <div className="auth-success">{success}</div>}
        
        {/* Step Indicator */}
        <div className="step-indicator">
          <div className={`step-dot ${step === 'form' ? 'active' : step === 'otp' ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step === 'otp' ? 'active' : ''}`}></div>
        </div>
        
        <form onSubmit={submit} className="auth-form">
          {/* Step 1: Registration Form */}
          {step === 'form' && (
            <>
              <div className="auth-input-group">
                <label className="auth-label">Username</label>
                <input
                  type="text"
                  className="auth-input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter your username"
                  required
                />
              </div>
              
              <div className="auth-input-group">
                <label className="auth-label">Email</label>
                <input
                  type="email"
                  className="auth-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter your email address"
                  required
                />
              </div>
              
              <div className="auth-input-group">
                <label className="auth-label">Password</label>
                <div className="password-input-container">
                  <input
                    type={showPassword ? "text" : "password"}
                    className="auth-input password-input"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    className="auth-password-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>
              
              <div className="auth-input-group">
                <label className="auth-label">Confirm Password</label>
                <div className="password-input-container">
                  <input
                    type={showConfirmPassword ? "text" : "password"}
                    className="auth-input password-input"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm your password"
                    required
                  />
                  <button
                    type="button"
                    className="auth-password-toggle"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                  >
                    {showConfirmPassword ? (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : (
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                        <line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </>
          )}

          {/* Step 2: OTP Verification */}
          {step === 'otp' && (
            <>
              <div className="auth-input-group">
                <label className="auth-label">OTP Code</label>
                <input
                  type="text"
                  className="auth-input"
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder="Enter 6-digit OTP"
                  maxLength={6}
                  required
                />
                <div className="otp-hint">
                  <p>We've sent a 6-digit code to <strong>{email}</strong></p>
                  <p>Check your email and enter the code above</p>
                </div>
              </div>
              
              <div className="auth-actions">
                <ResendButton
                  onResend={resendOTP}
                  countdown={countdown}
                  maxCountdown={60}
                  loading={loading}
                >
                  Resend OTP
                </ResendButton>
              </div>
            </>
          )}


          
          <button className="auth-button" type="submit" disabled={loading}>
            {loading && <span className="auth-loading"></span>}
            {step === 'form' && (loading ? "Sending OTP..." : "Send OTP")}
            {step === 'otp' && (loading ? "Verifying..." : "Verify OTP")}
          </button>
        </form>


        
        <div className="auth-link">
          <p>Already have an account? <Link to="/login">Sign in</Link></p>
        </div>
      </div>
    </div>
  );
}

// OTP Test Page Component
function OTPTestPage() {
  const [email, setEmail] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [step, setStep] = useState<'email' | 'otp' | 'success'>('email');

  const sendOTP = async () => {
    if (!email) {
      setMessage("Please enter an email address");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/send-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Failed to send OTP");
      }

      const data = await res.json();
      setStep('otp');
      setMessage(`OTP sent successfully! Check console for code: ${data.otp_code}`);
      console.log(`🔐 OTP sent to ${email}: ${data.otp_code}`);
    } catch (err: any) {
      setMessage(err?.message || "Failed to send OTP");
    } finally {
      setLoading(false);
    }
  };

  const verifyOTP = async () => {
    if (!otpCode) {
      setMessage("Please enter the OTP");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'}/auth/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp_code: otpCode })
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "OTP verification failed");
      }

      setStep('success');
      setMessage("OTP verified successfully!");
    } catch (err: any) {
      setMessage(err?.message || "OTP verification failed");
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setEmail("");
    setOtpCode("");
    setMessage("");
    setStep('email');
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-logo">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M12 2L13.09 8.26L20 9L13.09 9.74L12 16L10.91 9.74L4 9L10.91 8.26L12 2Z" fill="#4f46e5"/>
              <path d="M19 15L19.74 17.74L22.5 18.5L19.74 19.26L19 22L18.26 19.26L15.5 18.5L18.26 17.74L19 15Z" fill="#7c3aed"/>
              <path d="M5 6L5.37 7.37L6.74 7.74L5.37 8.11L5 9.48L4.63 8.11L3.26 7.74L4.63 7.37L5 6Z" fill="#10b981"/>
            </svg>
          </div>
          <h1 className="auth-title">OTP Test Page</h1>
          <p className="auth-subtitle">Test the OTP functionality</p>
        </div>
        
        {message && (
          <div className={`auth-${message.includes('successfully') ? 'success' : 'error'}`}>
            {message}
          </div>
        )}
        
        <div className="step-indicator">
          <div className={`step-dot ${step === 'email' ? 'active' : step === 'otp' || step === 'success' ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step === 'otp' ? 'active' : step === 'success' ? 'completed' : ''}`}></div>
          <div className={`step-dot ${step === 'success' ? 'active' : ''}`}></div>
        </div>
        
        {step === 'email' && (
          <div className="auth-form">
            <div className="auth-input-group">
              <label className="auth-label">Email Address</label>
              <input
                type="email"
                className="auth-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Enter email to test OTP"
                required
              />
            </div>
            
            <button 
              className="auth-button" 
              onClick={sendOTP} 
              disabled={loading}
            >
              {loading ? "Sending..." : "Send OTP"}
            </button>
          </div>
        )}
        
        {step === 'otp' && (
          <div className="auth-form">
            <div className="auth-input-group">
              <label className="auth-label">OTP Code</label>
              <input
                type="text"
                className="auth-input otp-input"
                value={otpCode}
                onChange={(e) => setOtpCode(e.target.value)}
                placeholder="Enter 6-digit OTP"
                maxLength={6}
                required
              />
              <div className="otp-hint">
                <p>OTP sent to <strong>{email}</strong></p>
                <p>Check console for the code</p>
              </div>
            </div>
            
            <button 
              className="auth-button" 
              onClick={verifyOTP} 
              disabled={loading}
            >
              {loading ? "Verifying..." : "Verify OTP"}
            </button>
          </div>
        )}
        
        {step === 'success' && (
          <div className="auth-form">
            <div className="verification-success">
              <div className="verification-icon">✅</div>
              <h3>OTP Test Successful!</h3>
              <p>The OTP system is working correctly.</p>
            </div>
            
            <button 
              className="auth-button" 
              onClick={resetForm}
            >
              Test Again
            </button>
          </div>
        )}
        
        <div className="auth-link">
          <p><Link to="/login">Back to Login</Link></p>
        </div>
      </div>
    </div>
  );
}
