import React, { useState } from 'react';
import AssistantHeader from './assistant/AssistantHeader';
import ConversationView from './assistant/ConversationView';
import SuggestedQuestions from './assistant/SuggestedQuestions';
import MessageComposer from './assistant/MessageComposer';

export default function AIAssistant() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');

  const formatTimestamp = () => {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const handleSendMessage = (text) => {
    if (!text || !text.trim()) return;

    const userMessage = {
      id: `user-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
      role: 'user',
      content: text.trim(),
      timestamp: formatTimestamp(),
    };

    const systemNotice = {
      id: `sys-${Date.now()}-${Math.random().toString(36).substr(2, 5)}`,
      role: 'system',
      content: 'Agent not connected. Real backend integration with LangChain and Domo AI will be enabled in Phase 7.',
      timestamp: formatTimestamp(),
    };

    setMessages((prev) => [...prev, userMessage, systemNotice]);
  };

  const handleClearChat = () => {
    setMessages([]);
  };

  return (
    <div className="ai-assistant-page">
      <AssistantHeader
        onClearChat={handleClearChat}
        messageCount={messages.length}
      />

      <div className="assistant-workspace-card">
        <ConversationView
          messages={messages}
          onSelectSuggestion={handleSendMessage}
        />

        <div className="assistant-bottom-dock">
          <SuggestedQuestions onSelectQuestion={handleSendMessage} />
          <MessageComposer
            input={input}
            setInput={setInput}
            onSendMessage={handleSendMessage}
          />
        </div>
      </div>
    </div>
  );
}
