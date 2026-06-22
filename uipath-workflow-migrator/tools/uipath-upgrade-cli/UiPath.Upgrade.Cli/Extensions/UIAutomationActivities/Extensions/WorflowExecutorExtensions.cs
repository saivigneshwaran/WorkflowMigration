using System.Collections.Generic;
using System.Threading.Tasks;

namespace UiPath.Activities.Contracts
{
    public static class WorflowExecutorExtensions
    {
        public static IDictionary<string, object> Execute(this IWorkflowExecutor workflowExecutor)
            => Task.Factory.FromAsync((callback, state) => workflowExecutor.BeginExecute(callback, state), (r) => workflowExecutor.EndExecute(r), null).Result;
    }
}
