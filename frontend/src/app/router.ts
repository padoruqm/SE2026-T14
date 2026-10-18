import { createRouter, createWebHistory } from 'vue-router'

import { UploadPage } from '@/features/upload'
import { ViewerPage } from '@/features/viewer'

export const routes = [
  { path: '/', redirect: '/upload' },
  { path: '/upload', name: 'upload', component: UploadPage },
  { path: '/viewer/:id', name: 'viewer', component: ViewerPage, props: true },
]

export function createAppRouter(history = createWebHistory()) {
  return createRouter({ history, routes })
}

export const router = createAppRouter()
