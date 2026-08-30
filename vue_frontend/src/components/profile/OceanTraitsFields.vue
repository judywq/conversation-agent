<template>
  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
    <FormField
      v-for="trait in OCEAN_TRAITS"
      :key="trait.key"
      v-slot="{ componentField, errorMessage }"
      :name="trait.key"
    >
      <FormItem>
        <FormLabel>{{ trait.label }}</FormLabel>
        <p class="text-xs text-muted-foreground">{{ trait.description }}</p>
        <Select v-bind="componentField">
          <FormControl>
            <SelectTrigger
              class="w-full"
              :class="errorMessage && 'border-destructive focus:ring-destructive'"
            >
              <SelectValue placeholder="Select a level" />
            </SelectTrigger>
          </FormControl>
          <SelectContent>
            <SelectItem v-for="lvl in OCEAN_LEVELS" :key="lvl" :value="lvl">
              {{ lvl }}
            </SelectItem>
          </SelectContent>
        </Select>
        <FormMessage />
      </FormItem>
    </FormField>
  </div>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  oceanFormSchema,
  oceanFormValuesFromModel,
  OCEAN_LEVELS,
  OCEAN_TRAITS,
  OCEAN_UNSET,
  type OceanFormValues,
  type OceanTraitKey,
} from '@/lib/profileForm'

const props = defineProps<{
  modelValue: Record<OceanTraitKey, string>
}>()

const form = useForm({
  validationSchema: toTypedSchema(oceanFormSchema),
  initialValues: oceanFormValuesFromModel(props.modelValue),
})

watch(
  () => props.modelValue,
  (ocean) => {
    form.resetForm({
      values: oceanFormValuesFromModel(ocean),
    })
  },
)

async function validateAndApply(): Promise<Record<OceanTraitKey, string> | null> {
  const result = await form.validate()
  if (!result.valid) return null

  const next: Record<OceanTraitKey, string> = {
    openness: OCEAN_UNSET,
    conscientiousness: OCEAN_UNSET,
    extraversion: OCEAN_UNSET,
    agreeableness: OCEAN_UNSET,
    neuroticism: OCEAN_UNSET,
  }
  const values = result.values
  if (!values) return null
  for (const { key } of OCEAN_TRAITS) {
    const v = values[key as keyof OceanFormValues]
    if (v) next[key] = v
  }
  return next
}

defineExpose({ validateAndApply })
</script>
