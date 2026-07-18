export const SCENE_OPTIONS = [
  { id: 'classroom', label: 'Sunny Classroom', url: '/scenes/classroom.png' },
  { id: 'library', label: 'Library Terrace', url: '/scenes/library.png' },
  { id: 'campus-cafe', label: 'Campus Café', url: '/scenes/campus-cafe.png' },
  { id: 'sports-ground', label: 'Sports Ground', url: '/scenes/sports-ground.png' },
  { id: 'meeting-room', label: 'Meeting Room', url: '/scenes/meeting-room.png' },
  { id: 'outdoors', label: 'Outdoors', url: '/scenes/outdoors.png' },
  { id: 'pathway', label: 'Pathway', url: '/scenes/pathway.png' },
] as const

export type SceneId = (typeof SCENE_OPTIONS)[number]['id']

export function randomSceneId(): SceneId {
  return SCENE_OPTIONS[Math.floor(Math.random() * SCENE_OPTIONS.length)].id
}
