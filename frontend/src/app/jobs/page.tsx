"use client";

import React, { useState, useEffect } from 'react';
import { 
  Plus, 
  Search, 
  MapPin, 
  Briefcase, 
  Star, 
  MoreVertical,
  Filter,
  ArrowRight,
  TrendingUp,
  Clock,
  CheckCircle2,
  AlertCircle,
  LucideIcon
} from 'lucide-react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Sidebar } from '@/components/layout/sidebar';
import { TopBar } from '@/components/layout/top-bar';
import { cn } from '@/lib/utils';
import { motion, AnimatePresence } from 'framer-motion';

const COLUMNS = [
  { id: 'shortlisted', title: 'Shortlisted', color: 'bg-indigo-500' },
  { id: 'contacted', title: 'Contacted', color: 'bg-purple-500' },
  { id: 'applied', title: 'Applied', color: 'bg-blue-500' },
  { id: 'interviewing', title: 'Interviewing', color: 'bg-amber-500' },
  { id: 'offer', title: 'Offer', color: 'bg-emerald-500' },
];

export default function JobsPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    api.jobs.list().then(setJobs).finally(() => setLoading(false));
  }, []);

  const filteredJobs = jobs.filter(j => 
    j.company.toLowerCase().includes(filter.toLowerCase()) || 
    j.role.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="flex min-h-screen bg-muted/30">
      <Sidebar />
      <main className="flex-1 pl-20 transition-all duration-300">
        <TopBar />
        
        <div className="p-8 h-[calc(100vh-80px)] overflow-hidden flex flex-col">
          {/* Kanban Header */}
          <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8 shrink-0">
            <div>
              <h1 className="text-3xl font-bold tracking-tight mb-2">Job Pipeline</h1>
              <p className="text-muted-foreground">Track your progress across {jobs.length} active roles.</p>
            </div>
            <div className="flex items-center gap-3">
               <div className="relative group">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                  <input 
                    type="text" 
                    placeholder="Filter jobs..." 
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    className="h-11 bg-background border rounded-2xl pl-10 pr-4 text-sm focus:ring-2 focus:ring-primary/20 outline-none w-64"
                  />
               </div>
               <Button variant="outline" className="rounded-2xl h-11">
                  <Filter className="w-4 h-4 mr-2" /> Filter
               </Button>
               <Button className="rounded-2xl h-11">
                  <Plus className="w-4 h-4 mr-2" /> Add Job
               </Button>
            </div>
          </header>

          {/* Kanban Board Container */}
          <div className="flex-1 overflow-x-auto pb-4 custom-scrollbar">
            <div className="flex gap-6 h-full min-w-[1250px]">
              {COLUMNS.map((col) => (
                <div key={col.id} className="w-80 flex flex-col h-full">
                  <div className="flex items-center justify-between mb-4 px-2">
                    <div className="flex items-center gap-2">
                      <div className={cn("w-2 h-2 rounded-full", col.color)} />
                      <h3 className="font-bold text-sm uppercase tracking-widest">{col.title}</h3>
                      <span className="text-xs font-bold text-muted-foreground bg-muted px-2 py-0.5 rounded-full tabular-nums">
                        {filteredJobs.filter(j => j.status === col.id).length}
                      </span>
                    </div>
                    <Button variant="ghost" size="icon" className="h-8 w-8 hover:bg-muted/50"><Plus className="w-4 h-4 text-muted-foreground" /></Button>
                  </div>

                  <div className="flex-1 bg-muted/20 border border-dashed rounded-[40px] p-4 overflow-y-auto custom-scrollbar flex flex-col gap-4">
                    {filteredJobs.filter(j => j.status === col.id).map((job) => (
                      <JobCard key={job.id} job={job} />
                    ))}
                    {filteredJobs.filter(j => j.status === col.id).length === 0 && (
                      <div className="flex-1 flex flex-col items-center justify-center text-center opacity-30 select-none">
                        <Briefcase className="w-12 h-12 mb-2" />
                        <p className="text-xs font-bold">No jobs here</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>

      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.05); border-radius: 10px; }
        .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.05); }
      `}</style>
    </div>
  );
}

function JobCard({ job }: { job: any }) {
  return (
    <motion.div 
      layoutId={job.id}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card bg-background border rounded-[28px] p-5 shadow-sm hover:shadow-xl hover:shadow-indigo-500/5 transition-all group cursor-grab active:cursor-grabbing border-b-4 border-b-primary/5"
    >
      <div className="flex justify-between items-start mb-4">
        <div className="w-10 h-10 rounded-xl bg-muted/30 flex items-center justify-center font-bold text-xs uppercase overflow-hidden border">
           {job.company[0]}
        </div>
        <div className={cn(
          "px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600",
          job.fit_score < 7 && "bg-amber-50 dark:bg-amber-900/20 text-amber-600"
        )}>
           Score: {job.fit_score}/10
        </div>
      </div>

      <div className="mb-4">
        <h4 className="font-bold text-sm mb-1 group-hover:underline underline-offset-4 decoration-primary/30 transition-all">{job.role}</h4>
        <p className="text-xs text-muted-foreground font-medium">{job.company}</p>
      </div>

      <div className="flex flex-wrap gap-2 mb-4">
        <div className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground bg-muted/50 px-2 py-1 rounded-lg">
          <MapPin className="w-3 h-3" /> {job.location || 'Remote'}
        </div>
        <div className="flex items-center gap-1 text-[10px] font-medium text-muted-foreground bg-muted/50 px-2 py-1 rounded-lg">
          <Star className="w-3 h-3 text-amber-500" /> High Fit
        </div>
      </div>

      <div className="flex items-center justify-between pt-4 border-t">
         <div className="flex -space-x-2">
            {[1, 2].map(i => (
              <div key={i} className="w-6 h-6 rounded-full border-2 border-background bg-slate-100 flex items-center justify-center text-[8px] font-bold">C{i}</div>
            ))}
            <div className="w-6 h-6 rounded-full border-2 border-background bg-muted flex items-center justify-center text-[8px] font-bold">+</div>
         </div>
         <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg group-hover:bg-primary group-hover:text-white transition-colors">
            <ArrowRight className="w-4 h-4" />
         </Button>
      </div>
    </motion.div>
  );
}
