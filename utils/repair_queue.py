"""
Repair Queue Management Module

This module provides data structures and utilities for managing batch repair
of code issues. It tracks individual issue repair attempts and maintains
a queue that is replenished from a pending pool.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from utils.TracePy import ExecutionResult, ResultStatus


@dataclass
class RepairTask:
    """
    Represents a single issue being repaired.
    
    Attributes:
        failure: The original ExecutionResult that failed
        repair_count: Number of repair attempts for this issue
        test_case_content: Used to identify/match the issue across test runs
    """
    failure: ExecutionResult
    repair_count: int = 0
    test_case_content: str = ""
    
    def __post_init__(self):
        """Initialize test_case_content from failure if not provided"""
        if not self.test_case_content and self.failure:
            self.test_case_content = self.failure.test_case


@dataclass
class RepairQueueState:
    """
    Manages the batch repair queue with active tasks and a pending pool.
    
    The queue maintains up to `max_size` active tasks being repaired concurrently.
    When tasks are completed or exceed max retries, they are removed and
    replenished from the pending pool to keep the queue full.
    
    Attributes:
        active_tasks: List of RepairTask currently being repaired (size <= max_size)
        pending_pool: List of ExecutionResult failures not yet in the active queue
        max_size: Maximum number of concurrent repairs (BATCH_SIZE)
        max_retries: Maximum repair attempts per issue before giving up
    """
    active_tasks: List[RepairTask] = field(default_factory=list)
    pending_pool: List[ExecutionResult] = field(default_factory=list)
    max_size: int = 3
    max_retries: int = 3
    
    def replenish(self) -> int:
        """
        Fill active_tasks from pending_pool until queue is full or pool is empty.
        
        Returns:
            Number of tasks added to the active queue
        """
        added_count = 0
        while len(self.active_tasks) < self.max_size and self.pending_pool:
            # Pop from front of pending pool (maintains priority order)
            failure = self.pending_pool.pop(0)
            task = RepairTask(failure=failure, repair_count=0)
            self.active_tasks.append(task)
            added_count += 1
            print(f"  [Queue] Added issue from the pending pool: {task.test_case_content[:50]}...")
        
        return added_count
    
    def remove_task(self, task: RepairTask) -> bool:
        """
        Remove a task from the active queue.
        
        Args:
            task: The RepairTask to remove
            
        Returns:
            True if task was found and removed, False otherwise
        """
        if task in self.active_tasks:
            self.active_tasks.remove(task)
            print(f"  [Queue] Removed issue: {task.test_case_content[:50]}...")
            return True
        return False
    
    def remove_task_by_content(self, test_case_content: str) -> Optional[RepairTask]:
        """
        Remove a task by its test case content.
        
        Args:
            test_case_content: The test case code string to match
            
        Returns:
            The removed RepairTask if found, None otherwise
        """
        for task in self.active_tasks:
            if task.test_case_content == test_case_content:
                self.active_tasks.remove(task)
                print(f"  [Queue] Removed issue: {test_case_content[:50]}...")
                return task
        return None
    
    def find_task_by_content(self, test_case_content: str) -> Optional[RepairTask]:
        """
        Find a task by its test case content without removing it.
        
        Args:
            test_case_content: The test case code string to match
            
        Returns:
            The RepairTask if found, None otherwise
        """
        for task in self.active_tasks:
            if task.test_case_content == test_case_content:
                return task
        return None
    
    def increment_retry(self, task: RepairTask) -> bool:
        """
        Increment the retry count for a task.
        
        Args:
            task: The RepairTask to increment
            
        Returns:
            True if still under max_retries, False if max reached
        """
        task.repair_count += 1
        return task.repair_count <= self.max_retries
    
    def get_active_failures(self) -> List[ExecutionResult]:
        """
        Get the list of ExecutionResult failures for all active tasks.
        
        Returns:
            List of ExecutionResult objects from active tasks
        """
        return [task.failure for task in self.active_tasks]
    
    def update_failure_for_task(self, test_case_content: str, new_failure: ExecutionResult) -> bool:
        """
        Update the failure object for a task (after re-running tests).
        
        Args:
            test_case_content: The test case content to match
            new_failure: The new ExecutionResult from the latest test run
            
        Returns:
            True if task was found and updated, False otherwise
        """
        task = self.find_task_by_content(test_case_content)
        if task:
            task.failure = new_failure
            return True
        return False
    
    def is_empty(self) -> bool:
        """Check if both active queue and pending pool are empty"""
        return len(self.active_tasks) == 0 and len(self.pending_pool) == 0
    
    def has_active_tasks(self) -> bool:
        """Check if there are any active tasks"""
        return len(self.active_tasks) > 0
    
    def get_stats(self) -> Dict[str, int]:
        """Get current queue statistics"""
        return {
            "active": len(self.active_tasks),
            "pending": len(self.pending_pool),
            "max_size": self.max_size
        }
    
    def remove_from_pending_by_content(self, test_case_content: str) -> bool:
        """
        Remove a failure from the pending pool by test case content.
        
        Args:
            test_case_content: The test case code string to match
            
        Returns:
            True if found and removed, False otherwise
        """
        for i, failure in enumerate(self.pending_pool):
            if failure.test_case == test_case_content:
                self.pending_pool.pop(i)
                print(f"  [Queue] Removed issue from the pending pool: {test_case_content[:50]}...")
                return True
        return False
