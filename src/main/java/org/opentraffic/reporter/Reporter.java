package org.opentraffic.reporter;

import java.util.Properties;

import org.apache.commons.cli.CommandLine;
import org.apache.commons.cli.CommandLineParser;
import org.apache.commons.cli.DefaultParser;
import org.apache.commons.cli.HelpFormatter;
import org.apache.commons.cli.Option;
import org.apache.commons.cli.Options;
import org.apache.commons.cli.ParseException;
import org.apache.kafka.clients.consumer.ConsumerConfig;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.processor.TopologyBuilder;

public class Reporter {
  
  public static CommandLine parse(String[] args) {
    Option bootstrap = new Option("b", "bootstrap", true, "Bootstrap servers config");
    bootstrap.setRequired(true);
    Option root_topic = new Option("r", "root-topic", true, "Root topic, where the raw custom format point messages come into the system");
    root_topic.setRequired(true);
    Option intermediate_topic = new Option("i", "intermediate-topic", true, "Intermediate topic, where the keyed-reformatted points are published");
    intermediate_topic.setRequired(true);
    Option leaf_topic = new Option("l", "leaf-topic", true, "Leaf topic, where the batched/windowed portions of a given keys points are published");
    leaf_topic.setRequired(true);
    Option url = new Option("u", "reporter-url", true, "The url to send batched/windowed portions of a given keys points to");
    url.setRequired(true);
    Option formatter = new Option("f", "formatter", true, "The formatter configuration separated args for constructing a custom formatter.\n"
        + "Separated value and json are currently supported.\n"
        + "To construct a seprated value formatter where the raw messages look like:\n"
        + "  2017-01-31 16:00:00|uuid_abcdef|x|x|x|accuracy|x|x|x|lat|lon|x|x|x\n"
        + "Specify a value of:\n"
        + "  --formatter \",sv,\\|,1,9,10,0,5,yyyy-MM-dd HH:mm:ss\"\n"
        + "To construct a json formatter where the raw messages look like:\n"
        + "  {\"timestamp\":1495037969,\"id\":\"uuid_abcdef\",\"accuracy\":51.305,\"latitude\":3.465725,\"longitude\":-76.5135033}\n"
        + "Specify a value of:\n"
        + "  --formatter \",json,id,latitude,longitude,timestamp,accuracy\"\n"
        + "Note that the time format string is optional, ie when your time value is already in epoch seconds");
    formatter.setRequired(true);
    url.setRequired(true);
    Option verbose = new Option("v", "verbose", false, "Creates a consumer that prints the leaf topic messages to the console");
    verbose.setRequired(false);
    Option duration = new Option("d", "duration", true, "How long to run the program in milliseconds, defaults to (essentially) forever");
    duration.setRequired(false);
    duration.setType(Long.class);
    
    Options options = new Options();
    options.addOption(bootstrap);
    options.addOption(root_topic);
    options.addOption(intermediate_topic);
    options.addOption(leaf_topic);
    options.addOption(url);
    options.addOption(formatter);
    options.addOption(verbose);
    options.addOption(duration);

    CommandLineParser parser = new DefaultParser();
    HelpFormatter help = new HelpFormatter();
    CommandLine cmd = null;

    try {
      cmd = parser.parse(options, args);
    }
    catch (ParseException e) {
      System.out.println(e.getMessage());
      help.printHelp("kafka-reporter", options);
      System.exit(1);
    }
    return cmd;
  }
  
  public static void main(String[] args) throws Exception {
    CommandLine cmd = parse(args);
    
    Properties props = new Properties();
    //for now lets just start streaming from the beginning instead of coming in mid stream
    props.put(ConsumerConfig.AUTO_OFFSET_RESET_CONFIG, "latest");
    //some init
    props.put(StreamsConfig.APPLICATION_ID_CONFIG, "reporter");
    props.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, cmd.getOptionValue("bootstrap"));
    props.put(StreamsConfig.KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass());
    props.put(StreamsConfig.VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass());

    //hook stuff together
    Point.Serder pointSerder = new Point.Serder();
    TopologyBuilder builder = new TopologyBuilder();
    
    //takes raw input from tnc and reformat the tnc format data into
    //a key of string type and a value of Point type
    builder.addSource("Source", new StringDeserializer(), new StringDeserializer(), cmd.getOptionValue("root-topic"));
    builder.addProcessor("Formatter", new KeyedFormattingProcessor(cmd), "Source");
    builder.addSink("KeyedPointsSink", cmd.getOptionValue("intermediate-topic"), new StringSerializer(), pointSerder.serializer(), "Formatter");
    
    //take batches of points for a given key (uuid) and when some threshold is met
    //send that batch of points off to the reporter to be matched and update the
    //batch according to how much of the batch was used in matching
    builder.addSource("KeyedPointsSource", new StringDeserializer(), pointSerder.deserializer(), cmd.getOptionValue("intermediate-topic"));
    builder.addProcessor("Batcher", new BatchingProcessor(cmd), "KeyedPointsSource");
    builder.addStateStore(BatchingProcessor.GetStore(), "Batcher");
    builder.addSink("Sink", cmd.getOptionValue("leaf-topic"), "Batcher");
    
    //start consuming
    if(cmd.hasOption("verbose")) {
      Thread consumer = new Thread(new PrintConsumer(cmd));
      consumer.setDaemon(true);
      consumer.start();
    }
    
    //start the topology
    KafkaStreams streams = new KafkaStreams(builder, props);
    streams.start();
    
    //wait a bit or basically forever
    long duration = Long.parseLong(cmd.getOptionValue("duration", Long.toString(Long.MAX_VALUE)));
    Thread.sleep(duration);

    //done
    pointSerder.close();
    streams.close();
  }
}