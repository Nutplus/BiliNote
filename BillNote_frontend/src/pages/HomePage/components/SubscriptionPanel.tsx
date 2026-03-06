import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'react-hot-toast'

import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import {
  pullLatestSubscriptionNote,
  fetchRecentSubscriptionNotes,
  mergeSubscriptionNotes,
} from '@/services/subscription'
import { useModelStore } from '@/store/modelStore'
import { useTaskStore } from '@/store/taskStore'

const schema = z.object({
  channel_url: z.string().url('请输入有效频道链接'),
  count: z.coerce.number().min(1, '至少抓取1条').max(20, '最多抓取20条').default(3),
  quality: z.enum(['fast', 'medium', 'slow']).default('medium'),
  style: z.string().optional(),
  extras: z.string().optional(),
  start_date: z.string().optional(),
  end_date: z.string().optional(),
  summarize: z.boolean().default(true),
})

type FormData = z.infer<typeof schema>

const SubscriptionPanel = () => {
  const modelList = useModelStore(state => state.modelList)
  const addPendingTask = useTaskStore(state => state.addPendingTask)
  const [loadingType, setLoadingType] = useState<'latest' | 'batch' | 'merge' | null>(null)

  const currentModel = useMemo(() => modelList?.[0], [modelList])

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      channel_url: 'https://www.youtube.com/@OpenAI/videos',
      count: 3,
      quality: 'medium',
      summarize: true,
    },
  })

  const guardModel = () => {
    if (!currentModel) {
      toast.error('请先在设置中配置模型')
      return false
    }
    return true
  }

  const onPullLatest = async (values: FormData) => {
    if (!guardModel()) return
    setLoadingType('latest')
    try {
      const res = await pullLatestSubscriptionNote({
        channel_url: values.channel_url,
        quality: values.quality,
        model_name: currentModel!.model_name,
        provider_id: currentModel!.provider_id,
        style: values.style,
        extras: values.extras,
      })

      if (res.status === 'no_update') {
        toast('暂无新视频')
        return
      }

      const taskId = res?.task?.task_id
      if (taskId) {
        addPendingTask(taskId, 'youtube', {
          video_url: res?.video?.video_url || values.channel_url,
          platform: 'youtube',
          quality: values.quality,
          model_name: currentModel!.model_name,
          provider_id: currentModel!.provider_id,
          style: values.style || 'minimal',
          format: [],
          link: false,
          screenshot: false,
          extras: values.extras || '',
        })
      }
      toast.success(res.message || '已拉取最新视频并生成笔记')
    } catch (e: any) {
      toast.error(e?.msg || '拉取最新视频失败')
    } finally {
      setLoadingType(null)
    }
  }

  const onFetchBatch = async (values: FormData) => {
    if (!guardModel()) return
    setLoadingType('batch')
    try {
      const res = await fetchRecentSubscriptionNotes({
        channel_url: values.channel_url,
        count: values.count,
        quality: values.quality,
        model_name: currentModel!.model_name,
        provider_id: currentModel!.provider_id,
        style: values.style,
        extras: values.extras,
      })
      const tasks = res?.tasks || []
      tasks.forEach(item => {
        const taskId = item?.task?.task_id
        if (!taskId) return
        addPendingTask(taskId, 'youtube', {
          video_url: item?.video?.video_url || values.channel_url,
          platform: 'youtube',
          quality: values.quality,
          model_name: currentModel!.model_name,
          provider_id: currentModel!.provider_id,
          style: values.style || 'minimal',
          format: [],
          link: false,
          screenshot: false,
          extras: values.extras || '',
        })
      })
      toast.success(res.message || `已提交 ${tasks.length} 个任务`)
    } catch (e: any) {
      toast.error(e?.msg || '批量抓取失败')
    } finally {
      setLoadingType(null)
    }
  }

  const onMerge = async (values: FormData) => {
    if (!values.start_date || !values.end_date) {
      toast.error('请先选择开始和结束日期')
      return
    }
    if (values.summarize && !guardModel()) return

    setLoadingType('merge')
    try {
      const res = await mergeSubscriptionNotes({
        channel_url: values.channel_url,
        start_date: values.start_date,
        end_date: values.end_date,
        summarize: values.summarize,
        model_name: values.summarize ? currentModel!.model_name : undefined,
        provider_id: values.summarize ? currentModel!.provider_id : undefined,
      })
      const summary = res?.summary ? `\n\n总结:\n${res.summary}` : ''
      toast.success(`合并完成: ${res.export_file || ''}${summary ? '' : ''}`)
    } catch (e: any) {
      toast.error(e?.msg || '合并导出失败')
    } finally {
      setLoadingType(null)
    }
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <h3 className="font-semibold">订阅一键笔记（YouTube）</h3>
      <Form {...form}>
        <form className="space-y-3">
          <FormField
            control={form.control}
            name="channel_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>频道链接</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="https://www.youtube.com/@xxx/videos" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <div className="grid grid-cols-2 gap-2">
            <FormField
              control={form.control}
              name="count"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>抓取数量</FormLabel>
                  <FormControl>
                    <Input type="number" min={1} max={20} {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="quality"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>清晰度</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="fast/medium/slow" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>

          <FormField
            control={form.control}
            name="extras"
            render={({ field }) => (
              <FormItem>
                <FormLabel>额外提示词（可选）</FormLabel>
                <FormControl>
                  <Textarea {...field} rows={2} />
                </FormControl>
              </FormItem>
            )}
          />

          <div className="flex gap-2">
            <Button
              type="button"
              disabled={loadingType !== null}
              onClick={form.handleSubmit(onPullLatest)}
              className="flex-1"
            >
              一键拉取最新并生成笔记
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={loadingType !== null}
              onClick={form.handleSubmit(onFetchBatch)}
              className="flex-1"
            >
              一键抓取最近N条
            </Button>
          </div>

          <div className="space-y-2 rounded-md border p-2">
            <div className="font-medium">日期范围合并导出</div>
            <div className="grid grid-cols-2 gap-2">
              <FormField
                control={form.control}
                name="start_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>开始日期</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="end_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>结束日期</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="summarize"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center gap-2 space-y-0">
                  <FormControl>
                    <Checkbox checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                  <FormLabel>自动AI二次总结</FormLabel>
                </FormItem>
              )}
            />

            <Button type="button" disabled={loadingType !== null} onClick={form.handleSubmit(onMerge)}>
              合并导出并总结
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}

export default SubscriptionPanel
