import { memo, useCallback, useState } from "react";
import {
  Edit,
  MoreHorizontal,
  Trash2,
  Pause,
  Archive,
  Play,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/hooks/use-toast";
import { useMemoriesApi } from "@/hooks/useMemoriesApi";
import { useDispatch, useSelector } from "react-redux";
import { RootState } from "@/store/store";
import {
  selectMemory,
  deselectMemory,
  selectAllMemories,
  clearSelection,
} from "@/store/memoriesSlice";
import SourceApp from "@/components/shared/source-app";
import { HiMiniRectangleStack } from "react-icons/hi2";
import { PiSwatches } from "react-icons/pi";
import { GoPackage } from "react-icons/go";
import { CiCalendar } from "react-icons/ci";
import { useRouter } from "next/navigation";
import Categories from "@/components/shared/categories";
import { useUI } from "@/hooks/useUI";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatDate } from "@/lib/helpers";
import type { Memory } from "@/components/types";

interface MemoryRowProps {
  memory: Memory;
  isSelected: boolean;
  isLoading: boolean;
  onSelect: (id: string, checked: boolean) => void;
  onOpen: (id: string) => void;
  onUpdateState: (id: string, newState: string) => void;
  onEdit: (id: string, content: string) => void;
  onRequestDelete: (id: string) => void;
}

// Memoized so a selection change re-renders only the two affected rows instead
// of every row on the page (each row carries a dropdown + category chips, so a
// full-page re-render is visibly janky at size=50/100).
const MemoryRow = memo(function MemoryRow({
  memory,
  isSelected,
  isLoading,
  onSelect,
  onOpen,
  onUpdateState,
  onEdit,
  onRequestDelete,
}: MemoryRowProps) {
  const isInactive = memory.state === "paused" || memory.state === "archived";

  return (
    <TableRow
      className={`hover:bg-zinc-900/50 ${isInactive ? "text-zinc-400" : ""} ${
        isLoading ? "animate-pulse opacity-50" : ""
      }`}
    >
      <TableCell className="pl-4">
        <Checkbox
          className="data-[state=checked]:border-primary border-zinc-500/50"
          checked={isSelected}
          onCheckedChange={(checked) => onSelect(memory.id, checked as boolean)}
        />
      </TableCell>
      <TableCell className="">
        {isInactive ? (
          <Tooltip delayDuration={0}>
            <TooltipTrigger asChild>
              <div
                onClick={() => onOpen(memory.id)}
                className="font-medium text-zinc-400 cursor-pointer"
              >
                {memory.memory}
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>
                This memory is{" "}
                <span className="font-bold">
                  {memory.state === "paused" ? "paused" : "archived"}
                </span>{" "}
                and <span className="font-bold">disabled</span>.
              </p>
            </TooltipContent>
          </Tooltip>
        ) : (
          <div
            onClick={() => onOpen(memory.id)}
            className="font-medium text-white cursor-pointer"
          >
            {memory.memory}
          </div>
        )}
      </TableCell>
      <TableCell className="">
        <div className="flex flex-wrap gap-1">
          <Categories
            categories={memory.categories}
            isPaused={isInactive}
            concat={true}
          />
        </div>
      </TableCell>
      <TableCell className="w-[140px] text-center">
        <SourceApp source={memory.app_name} />
      </TableCell>
      <TableCell className="w-[140px] text-center">
        {formatDate(memory.created_at)}
      </TableCell>
      <TableCell className="text-right flex justify-center">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="bg-zinc-900 border-zinc-800"
          >
            <DropdownMenuItem
              className="cursor-pointer"
              onClick={() => {
                const newState =
                  memory.state === "active" ? "paused" : "active";
                onUpdateState(memory.id, newState);
              }}
            >
              {memory?.state === "active" ? (
                <>
                  <Pause className="mr-2 h-4 w-4" />
                  Pause
                </>
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" />
                  Resume
                </>
              )}
            </DropdownMenuItem>
            <DropdownMenuItem
              className="cursor-pointer"
              onClick={() => {
                const newState =
                  memory.state === "active" ? "archived" : "active";
                onUpdateState(memory.id, newState);
              }}
            >
              <Archive className="mr-2 h-4 w-4" />
              {memory?.state !== "archived" ? <>Archive</> : <>Unarchive</>}
            </DropdownMenuItem>
            <DropdownMenuItem
              className="cursor-pointer"
              onClick={() => onEdit(memory.id, memory.memory)}
            >
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="cursor-pointer text-red-500 focus:text-red-500"
              onClick={() => onRequestDelete(memory.id)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
});

export function MemoryTable() {
  const { toast } = useToast();
  const router = useRouter();
  const dispatch = useDispatch();
  const selectedMemoryIds = useSelector(
    (state: RootState) => state.memories.selectedMemoryIds
  );
  const memories = useSelector((state: RootState) => state.memories.memories);

  const { deleteMemories, updateMemoryState, isLoading } = useMemoriesApi();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const handleConfirmDelete = async () => {
    if (!pendingDeleteId) return;
    const id = pendingDeleteId;
    setPendingDeleteId(null);
    try {
      await deleteMemories([id]);
      toast({
        title: "Memory deleted",
        description: "The memory has been permanently deleted.",
      });
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete memory",
        variant: "destructive",
      });
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      dispatch(selectAllMemories());
    } else {
      dispatch(clearSelection());
    }
  };

  const handleSelectMemory = useCallback(
    (id: string, checked: boolean) => {
      if (checked) {
        dispatch(selectMemory(id));
      } else {
        dispatch(deselectMemory(id));
      }
    },
    [dispatch]
  );
  const { handleOpenUpdateMemoryDialog } = useUI();

  const handleEditMemory = useCallback(
    (memory_id: string, memory_content: string) => {
      handleOpenUpdateMemoryDialog(memory_id, memory_content);
    },
    [handleOpenUpdateMemoryDialog]
  );

  const handleUpdateMemoryState = useCallback(
    async (id: string, newState: string) => {
      try {
        await updateMemoryState([id], newState);
      } catch (error) {
        toast({
          title: "Error",
          description: "Failed to update memory state",
          variant: "destructive",
        });
      }
    },
    [updateMemoryState, toast]
  );

  const isAllSelected =
    memories.length > 0 && selectedMemoryIds.length === memories.length;
  const isPartiallySelected =
    selectedMemoryIds.length > 0 && selectedMemoryIds.length < memories.length;

  const handleMemoryClick = useCallback(
    (id: string) => {
      router.push(`/memory/${id}`);
    },
    [router]
  );

  const handleRequestDelete = useCallback((id: string) => {
    setPendingDeleteId(id);
  }, []);

  return (
    <>
    <div className="rounded-md border">
      {/* One provider for the whole table — previously each paused/archived row
          mounted its own TooltipProvider. */}
      <TooltipProvider>
      <Table className="">
        <TableHeader>
          <TableRow className="bg-zinc-800 hover:bg-zinc-800">
            <TableHead className="w-[50px] pl-4">
              <Checkbox
                className="data-[state=checked]:border-primary border-zinc-500/50"
                checked={isAllSelected}
                data-state={
                  isPartiallySelected
                    ? "indeterminate"
                    : isAllSelected
                    ? "checked"
                    : "unchecked"
                }
                onCheckedChange={handleSelectAll}
              />
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center min-w-[600px]">
                <HiMiniRectangleStack className="mr-1" />
                Memory
              </div>
            </TableHead>
            <TableHead className="border-zinc-700">
              <div className="flex items-center">
                <PiSwatches className="mr-1" size={15} />
                Categories
              </div>
            </TableHead>
            <TableHead className="w-[140px] border-zinc-700">
              <div className="flex items-center">
                <GoPackage className="mr-1" />
                Source App
              </div>
            </TableHead>
            <TableHead className="w-[140px] border-zinc-700">
              <div className="flex items-center w-full justify-center">
                <CiCalendar className="mr-1" size={16} />
                Created On
              </div>
            </TableHead>
            <TableHead className="text-right border-zinc-700 flex justify-center">
              <div className="flex items-center justify-end">
                <MoreHorizontal className="h-4 w-4 mr-2" />
              </div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {memories.map((memory) => (
            <MemoryRow
              key={memory.id}
              memory={memory}
              isSelected={selectedMemoryIds.includes(memory.id)}
              isLoading={isLoading}
              onSelect={handleSelectMemory}
              onOpen={handleMemoryClick}
              onUpdateState={handleUpdateMemoryState}
              onEdit={handleEditMemory}
              onRequestDelete={handleRequestDelete}
            />
          ))}
        </TableBody>
      </Table>
      </TooltipProvider>
    </div>
      <AlertDialog
        open={pendingDeleteId !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDeleteId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this memory?</AlertDialogTitle>
            <AlertDialogDescription>
              This permanently deletes the memory. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              className="bg-red-600 hover:bg-red-700"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
