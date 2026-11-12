/**
 * AI Assistant Chat API service for Industrial Energy Intelligence Platform.
 * Communicates with FastAPI backend through the Vite reverse proxy (/api/assistant/chat).
 */

import { apiRequest } from './apiClient';

/**
 * Send a user message and bounded conversation history to the AI Assistant.
 *
 * @param {object} params
 * @param {string} params.message - The natural-language query.
 * @param {string} [params.conversation_id] - Optional UUID string tracking the conversation.
 * @param {Array<{role: 'user'|'assistant', content: string}>} [params.history=[]] - Bounded conversation history (max 10 turns).
 * @returns {Promise<{
 *   conversation_id: string,
 *   answer: string,
 *   tool_references: string[],
 *   tool_evidence: Array<{
 *     tool_name: string,
 *     execution_order: number,
 *     success: boolean,
 *     summary?: string
 *   }>,
 *   tool_count: number,
 *   model_call_count: number,
 *   execution_limit_reached: boolean
 * }>}
 */
export async function sendAssistantMessage({ message, conversation_id = null, history = [] }) {
  if (!message || typeof message !== 'string' || !message.trim()) {
    throw new Error('Message cannot be empty.');
  }

  const payload = {
    message: message.trim(),
    ...(conversation_id ? { conversation_id } : {}),
    history: Array.isArray(history)
      ? history.slice(-10).map((h) => ({
          role: h.role === 'assistant' ? 'assistant' : 'user',
          content: String(h.content || '').trim(),
        }))
      : [],
  };

  return apiRequest('/assistant/chat', {
    init: {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    },
  });
}

export const assistantApi = {
  sendMessage: sendAssistantMessage,
};

export default assistantApi;
