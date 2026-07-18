export const SCENE_OPTIONS = [
  { id: 'classroom', label: 'Sunny Classroom', url: '/scenes/classroom.png' },
  { id: 'lecture-classroom', label: 'Lecture Classroom', url: '/scenes/lecture-classroom.png' },
  { id: 'library1', label: 'Library 1', url: '/scenes/library1.png' },
  { id: 'library2', label: 'Library 2', url: '/scenes/library2.png' },
  { id: 'campus-cafe', label: 'Campus Café', url: '/scenes/campus-cafe.png' },
  { id: 'study-lounge', label: 'Study Lounge', url: '/scenes/study-lounge.png' },
  { id: 'sports-ground1', label: 'Sports Ground 1', url: '/scenes/sports-ground1.png' },
  { id: 'sports-ground2', label: 'Sports Ground 2', url: '/scenes/sports-ground2.png' },
  { id: 'meeting-room', label: 'Meeting Room', url: '/scenes/meeting-room.png' },
  { id: 'science-lab', label: 'Science Lab', url: '/scenes/science-lab.png' },
  { id: 'clocktower', label: 'Clocktower', url: '/scenes/clocktower.png' },
  { id: 'pathway', label: 'Pathway', url: '/scenes/pathway.png' },
] as const

export type SceneId = (typeof SCENE_OPTIONS)[number]['id']

export function randomSceneId(): SceneId {
  return SCENE_OPTIONS[Math.floor(Math.random() * SCENE_OPTIONS.length)].id
}
