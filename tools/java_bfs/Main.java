import java.util.Scanner;

/**
 * Created by oc on 2017/10/12.
 */
public class Main {
    
    public static void main(String[] args){
        boolean shouldMerge=true, shouldEat=true, summary=false, batch=false, quiet=false;
        for (String string: args) {
            if ("--nomerge".equals(string)) shouldMerge=false;
            if ("--noeat".equals(string)) shouldEat=false;
            if ("--summary".equals(string)) summary=true;
            if ("--batch".equals(string)) batch=true;
            if ("--quiet".equals(string)) quiet=true;
        }

        Scanner scanner=new Scanner(System.in);
        if (batch) {
            // one JVM for many maps: each map is a complete input file, answered by one RESULT line
            while (scanner.hasNextInt()) new Graph(scanner, shouldMerge, shouldEat).runSummary(quiet);
            return;
        }
        Graph graph=new Graph(scanner, shouldMerge, shouldEat);
        if (summary) {
            graph.runSummary(quiet);
            return;
        }

        System.out.println("------ Printing Nodes ------");

        int valid=0;

        for (Node node: graph.list) {
            System.out.println(node);
            if (!node.doors.isEmpty() || !node.monsters.isEmpty())
                valid++;
        }


        System.out.println(valid+"/"+graph.list.size()+" nodes in total.");

        graph.run();

    }
    
}
