import React, { useRef, useState } from 'react';
import AssistantHeader from './assistant/AssistantHeader';
import ConversationView from './assistant/ConversationView';
import MessageComposer from './assistant/MessageComposer';
import { sendAssistantMessage } from '../services/assistantApi';
import './assistant/assistant.css';

export default function AIAssistant({ theme, onToggleTheme }) {
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastFailedMessage, setLastFailedMessage] = useState(null);
  const [input, setInput] = useState('');
  const conversationRef = useRef(null);

  const formatTimestamp = () => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const handleSendMessage = async (text) => {
    const trimmed = (text || '').trim();
    if (!trimmed || isLoading) return;

    // 1. Create and render user question
    const userMessageId = `user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
    const userMessage = {
      id: userMessageId,
      role: 'user',
      content: trimmed,
      timestamp: formatTimestamp(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);
    setLastFailedMessage(null);
    window.requestAnimationFrame(() => conversationRef.current?.focus());

    // 2. Extract bounded conversation history (max 10 previous turns, excluding current query)
    const validHistory = messages
      .filter((m) => (m.role === 'user' || m.role === 'assistant') && !m.isError)
      .slice(-10)
      .map((m) => ({
        role: m.role,
        content: m.content,
      }));

    try {
      // 3. Submit request to backend ReAct API
      const response = await sendAssistantMessage({
        message: trimmed,
        conversation_id: conversationId,
        history: validHistory,
      });

      // 4. Update conversation ID and add assistant response
      if (response.conversation_id) {
        setConversationId(response.conversation_id);
      }

      const assistantMessageId = `asst-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
      const assistantMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: response.answer,
        timestamp: formatTimestamp(),
        tool_references: response.tool_references || [],
        tool_evidence: response.tool_evidence || [],
        tool_count: response.tool_count || 0,
        model_call_count: response.model_call_count || 0,
        execution_limit_reached: Boolean(response.execution_limit_reached),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      console.error('Assistant chat failed:', err);
      const errorText = err.message || 'Unable to communicate with the AI assistant. Please try again.';
      setError(errorText);
      setLastFailedMessage(trimmed);

      const errorMessageId = `err-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`;
      const errorMessage = {
        id: errorMessageId,
        role: 'assistant',
        content: `**Request Failed:** ${errorText}\n\nYou can click **Retry Query** below to submit this question again without retyping.`,
        timestamp: formatTimestamp(),
        isError: true,
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (lastFailedMessage && !isLoading) {
      // Remove the last error message from the list before retrying
      setMessages((prev) => prev.filter((m) => !m.isError));
      handleSendMessage(lastFailedMessage);
    }
  };

  const handleNewConversation = () => {
    setMessages([]);
    setConversationId(null);
    setError(null);
    setLastFailedMessage(null);
    setInput('');
  };

  return (
    <div className="ai-assistant-page">
      <AssistantHeader
        onNewConversation={handleNewConversation}
        messageCount={messages.length}
        theme={theme}
        onToggleTheme={onToggleTheme}
      />

      <ConversationView
        conversationRef={conversationRef}
        messages={messages}
        isLoading={isLoading}
      />

      {lastFailedMessage && !isLoading && (
        <div className="assistant-retry-banner" role="alert">
          <div className="retry-banner-text">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>Last query encountered an error.</span>
          </div>
          <div className="retry-banner-actions">
            <button
              type="button"
              className="assistant-retry-btn"
              onClick={handleRetry}
            >
              Retry Query
            </button>
            <button
              type="button"
              className="assistant-dismiss-btn"
              onClick={() => setLastFailedMessage(null)}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <MessageComposer
        input={input}
        setInput={setInput}
        onSendMessage={handleSendMessage}
        onSelectSuggestion={handleSendMessage}
        disabled={isLoading}
      />
    </div>
  );
}
