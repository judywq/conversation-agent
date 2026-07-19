export const SCENE_OPTIONS = [
  {
    id: 'classroom',
    label: 'Sunny Classroom',
    url: '/scenes/classroom.webp',
    thumbUrl: '/scenes/classroom.thumb.webp',
  },
  {
    id: 'lecture-classroom',
    label: 'Lecture Classroom',
    url: '/scenes/lecture-classroom.webp',
    thumbUrl: '/scenes/lecture-classroom.thumb.webp',
  },
  {
    id: 'library1',
    label: 'Library 1',
    url: '/scenes/library1.webp',
    thumbUrl: '/scenes/library1.thumb.webp',
  },
  {
    id: 'library2',
    label: 'Library 2',
    url: '/scenes/library2.webp',
    thumbUrl: '/scenes/library2.thumb.webp',
  },
  {
    id: 'campus-cafe',
    label: 'Campus Café',
    url: '/scenes/campus-cafe.webp',
    thumbUrl: '/scenes/campus-cafe.thumb.webp',
  },
  {
    id: 'study-lounge',
    label: 'Study Lounge',
    url: '/scenes/study-lounge.webp',
    thumbUrl: '/scenes/study-lounge.thumb.webp',
  },
  {
    id: 'sports-ground1',
    label: 'Sports Ground 1',
    url: '/scenes/sports-ground1.webp',
    thumbUrl: '/scenes/sports-ground1.thumb.webp',
  },
  {
    id: 'sports-ground2',
    label: 'Sports Ground 2',
    url: '/scenes/sports-ground2.webp',
    thumbUrl: '/scenes/sports-ground2.thumb.webp',
  },
  {
    id: 'meeting-room',
    label: 'Meeting Room',
    url: '/scenes/meeting-room.webp',
    thumbUrl: '/scenes/meeting-room.thumb.webp',
  },
  {
    id: 'science-lab',
    label: 'Science Lab',
    url: '/scenes/science-lab.webp',
    thumbUrl: '/scenes/science-lab.thumb.webp',
  },
  {
    id: 'clocktower',
    label: 'Clocktower',
    url: '/scenes/clocktower.webp',
    thumbUrl: '/scenes/clocktower.thumb.webp',
  },
  {
    id: 'pathway',
    label: 'Pathway',
    url: '/scenes/pathway.webp',
    thumbUrl: '/scenes/pathway.thumb.webp',
  },
] as const

export type SceneId = (typeof SCENE_OPTIONS)[number]['id']

export function randomSceneId(): SceneId {
  return SCENE_OPTIONS[Math.floor(Math.random() * SCENE_OPTIONS.length)].id
}
