import axios from 'axios';

let csrfToken = '';
const api = axios.create({
  baseURL: '',
  timeout: 140000,
  withCredentials: true,
  headers: { 'X-Requested-With': 'DocMind' },
});
api.interceptors.request.use(config => {
  if (csrfToken) config.headers['X-CSRF-Token'] = csrfToken;
  return config;
});
api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && !error.config.url.endsWith('/login')) {
    csrfToken = '';
    window.dispatchEvent(new Event('docmind:session-expired'));
  }
  return Promise.reject(error);
});
const session = response => {
  csrfToken = response.data.csrf_token;
  return response.data;
};
export const authApi = {
  me: () => api.get('/api/auth/me').then(session),
  login: (email, password) => api.post('/api/auth/login', { email, password }).then(session),
  logout: async () => { await api.post('/api/auth/logout'); csrfToken = ''; },
};
export const errorMessage = error => {
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map(item => item.msg).join('; ');
  return error.code === 'ECONNABORTED'
    ? 'The request timed out. Refresh to check whether it completed before trying again.'
    : 'Unable to connect. Please try again.';
};
export const documentApi = {
  upload: file => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/documents/upload', formData);
  },
  list: (offset = 0, limit = 50, signal) => api.get('/api/documents/', { params: { offset, limit }, signal }),
  delete: id => api.delete(`/api/documents/${id}`),
  retry: id => api.post(`/api/documents/${id}/retry`),
  chunk: (id, index) => api.get(`/api/documents/${id}/chunks`, { params: { chunk_index: index, limit: 1 } }),
};
export const chatApi = {
  listConversations: (offset = 0) => api.get('/api/chat/', { params: { offset, limit: 50 } }),
  createConversation: () => api.post('/api/chat/', { title: 'New Conversation' }),
  deleteConversation: id => api.delete(`/api/chat/${id}`),
  getHistory: (id, offset = 0, signal) => api.get(`/api/chat/${id}/history`, { params: { offset, limit: 50 }, signal }),
  sendMessage: (id, content, queryMode, documentIds, requestId) =>
    api.post(`/api/chat/${id}/message`, {
      content, query_mode: queryMode, document_ids: documentIds, request_id: requestId,
    }),
};
